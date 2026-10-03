"""Harmonic Reference — reference matching in the note domain.

Auralis already matches a reference track's *frequency spectrum* (see
``mastering.py`` / Matchering). This module is the same idea one axis over: it
compares what **notes** two tracks use and reports what to change, rather than
what EQ to apply.

The one decision that makes the comparison musically meaningful: pitch-class
weights are rotated into **scale degrees relative to each track's own tonic**
before anything is compared. A song in F minor and a song in C minor use almost
no absolute pitches in common, yet may be harmonically identical — comparing raw
pitch classes would report a huge difference that means nothing. Comparing
degrees ("how much do you lean on the ♭3 vs the 5") is the comparison a musician
would actually make.

Everything here is deterministic DSP. No model, no LLM — same rule as the rest
of the engine, and no dependency on the API or frontend.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

try:
    import librosa
except ImportError:  # keeps the module importable for docs/tests without audio deps
    librosa = None


# Reuse the vocabulary the tuning stage already established so reports agree.
KEY_NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
DEGREE_NAMES = ["1", "♭2", "2", "♭3", "3", "4", "♭5", "5", "♭6", "6", "♭7", "7"]
SCALES = {
    "major": {0, 2, 4, 5, 7, 9, 11},
    "minor": {0, 2, 3, 5, 7, 8, 10},
}

# A degree has to be off by more than this share of total tonal energy before it
# is worth mentioning. Chroma estimates are noisy; below this the "difference"
# is measurement error, and reporting it would train the user to ignore the tool.
DEGREE_REPORT_THRESHOLD = 0.035
# Above this, the imbalance is the dominant harmonic difference between the two.
DEGREE_HIGH_THRESHOLD = 0.075


@dataclass
class OutOfKeyNote:
    """One sung/played note that falls outside the detected key."""
    start_seconds: float
    end_seconds: float
    detected_note: str
    detected_midi: float
    nearest_in_key_note: str
    nearest_in_key_midi: int
    cents_away: float
    confidence: float


@dataclass
class HarmonyAnalysis:
    """What one track is doing harmonically."""
    key_name: str
    key_tonic: int
    key_mode: str
    key_confidence: float

    # Pitch-class energy, index 0 = C. Sums to 1.
    chroma: list[float] = field(default_factory=list)
    # The same energy rotated so index 0 = this track's tonic. Sums to 1.
    # THIS is what cross-track comparison uses.
    degree_weights: list[float] = field(default_factory=list)

    # Share of tonal energy sitting outside the detected scale.
    out_of_key_energy: float = 0.0

    # Melodic register, in MIDI note numbers. None when no melody was found.
    median_midi: float | None = None
    low_midi: float | None = None
    high_midi: float | None = None
    note_count: int = 0

    out_of_key_notes: list[OutOfKeyNote] = field(default_factory=list)


@dataclass
class NoteSuggestion:
    """One actionable change, in the same spirit as a mastering suggestion."""
    kind: str          # transpose | mode | degree | out_of_key | register
    severity: str      # high | medium | low
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class HarmonyComparison:
    target: HarmonyAnalysis
    reference: HarmonyAnalysis
    # Semitones to shift the target so its tonic lands on the reference's.
    # Always the shortest path, so -5 is preferred over +7.
    suggested_transpose: int
    # Per-degree (target - reference) share of tonal energy.
    degree_deltas: list[float]
    suggestions: list[NoteSuggestion]


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse_harmony(
    audio: np.ndarray,
    sr: int,
    key_override=None,
    detect_notes: bool = True,
) -> HarmonyAnalysis:
    """Describe a track's harmony: key, degree usage, register, stray notes.

    ``key_override`` accepts a ``KeyEstimate``-shaped object (anything with
    ``tonic``/``mode``/``name``/``confidence``) so a user-declared key beats
    detection, matching how Pitch Polish already behaves.
    """
    if librosa is None:
        raise RuntimeError("librosa is required for harmonic analysis")

    mono = _mono(audio)
    if mono.size < sr // 4:
        raise ValueError("Track is too short to analyse harmonically.")

    if key_override is not None:
        tonic = int(key_override.tonic)
        mode = str(key_override.mode)
        key_name = getattr(key_override, "name", f"{KEY_NAMES[tonic]} {mode}")
        key_conf = float(getattr(key_override, "confidence", 1.0))
    else:
        # Defer to the existing detector so a track never reports two different
        # keys depending on which feature the user opened.
        from ..voice.pitch import detect_key
        estimate = detect_key(mono, sr, source="reference")
        tonic, mode = estimate.tonic, estimate.mode
        key_name, key_conf = estimate.name, estimate.confidence

    chroma = _chroma_profile(mono, sr)
    degrees = np.roll(chroma, -tonic)
    allowed = SCALES.get(mode, SCALES["major"])
    out_of_key_energy = float(sum(degrees[i] for i in range(12) if i not in allowed))

    median_midi = low_midi = high_midi = None
    notes: list[dict] = []
    if detect_notes:
        notes = _detect_notes(mono, sr)
        if notes:
            centers = np.array([n["midi"] for n in notes], dtype=float)
            median_midi = float(np.median(centers))
            low_midi = float(np.min(centers))
            high_midi = float(np.max(centers))

    return HarmonyAnalysis(
        key_name=key_name,
        key_tonic=tonic,
        key_mode=mode,
        key_confidence=round(float(key_conf), 3),
        chroma=[round(float(v), 5) for v in chroma],
        degree_weights=[round(float(v), 5) for v in degrees],
        out_of_key_energy=round(out_of_key_energy, 5),
        median_midi=None if median_midi is None else round(median_midi, 2),
        low_midi=None if low_midi is None else round(low_midi, 2),
        high_midi=None if high_midi is None else round(high_midi, 2),
        note_count=len(notes),
        out_of_key_notes=_stray_notes(notes, tonic, allowed),
    )


def compare_to_reference(
    target_audio: np.ndarray,
    target_sr: int,
    reference_audio: np.ndarray,
    reference_sr: int,
    target_key=None,
    reference_key=None,
) -> HarmonyComparison:
    """Analyse both tracks and report what to change in the target."""
    target = analyse_harmony(target_audio, target_sr, key_override=target_key)
    # Note detection has to run on the reference too. An earlier version skipped
    # it "since the reference's stray notes aren't the user's problem" — true,
    # but the register comparison needs the reference's median pitch, so that
    # optimisation silently made the octave-displacement suggestion unreachable.
    # Cost is bounded by the window cap inside _detect_notes instead.
    reference = analyse_harmony(
        reference_audio, reference_sr, key_override=reference_key,
    )
    transpose = _shortest_transpose(target.key_tonic, reference.key_tonic)
    deltas = [
        round(float(t - r), 5)
        for t, r in zip(target.degree_weights, reference.degree_weights)
    ]
    return HarmonyComparison(
        target=target,
        reference=reference,
        suggested_transpose=transpose,
        degree_deltas=deltas,
        suggestions=_build_suggestions(target, reference, transpose, deltas),
    )


def comparison_to_dict(comparison: HarmonyComparison) -> dict:
    """JSON-ready form, for the API and the on-disk report."""
    return {
        "target": asdict(comparison.target),
        "reference": asdict(comparison.reference),
        "suggested_transpose": comparison.suggested_transpose,
        "degree_deltas": comparison.degree_deltas,
        "degree_names": DEGREE_NAMES,
        "suggestions": [asdict(s) for s in comparison.suggestions],
    }


# ── Suggestion building ───────────────────────────────────────────────────────

def _build_suggestions(
    target: HarmonyAnalysis,
    reference: HarmonyAnalysis,
    transpose: int,
    deltas: list[float],
) -> list[NoteSuggestion]:
    out: list[NoteSuggestion] = []

    # 1. Key / transposition.
    if transpose != 0:
        direction = "up" if transpose > 0 else "down"
        other = transpose - 12 if transpose > 0 else transpose + 12
        out.append(NoteSuggestion(
            kind="transpose",
            severity="high",
            message=(
                f"You're in {target.key_name}; the reference is in "
                f"{reference.key_name}. Transpose {direction} "
                f"{abs(transpose)} semitone{'s' if abs(transpose) != 1 else ''} "
                f"to sit in the same key (or {abs(other)} the other way)."
            ),
            detail={
                "semitones": transpose,
                "alternative_semitones": other,
                "from_key": target.key_name,
                "to_key": reference.key_name,
            },
        ))
    else:
        out.append(NoteSuggestion(
            kind="transpose",
            severity="low",
            message=f"Same tonic as the reference ({target.key_name}). No transposition needed.",
            detail={"semitones": 0},
        ))

    # 2. Mode. Separate from tonic on purpose — C major and C minor share a
    #    tonic but are not interchangeable, and a transpose won't fix it.
    if target.key_mode != reference.key_mode:
        out.append(NoteSuggestion(
            kind="mode",
            severity="high",
            message=(
                f"The reference is {reference.key_mode}, yours is {target.key_mode}. "
                f"That's a different colour, not a pitch offset — transposing won't "
                f"fix it. Re-voice the 3rd (and 6th/7th) to move between them."
            ),
            detail={"target_mode": target.key_mode, "reference_mode": reference.key_mode},
        ))

    # 3. Degree balance — the per-band EQ delta of this feature.
    ranked = sorted(
        range(12), key=lambda i: abs(deltas[i]), reverse=True
    )
    for index in ranked:
        delta = deltas[index]
        if abs(delta) < DEGREE_REPORT_THRESHOLD:
            break
        severity = "high" if abs(delta) >= DEGREE_HIGH_THRESHOLD else "medium"
        degree = DEGREE_NAMES[index]
        target_pct = target.degree_weights[index] * 100
        ref_pct = reference.degree_weights[index] * 100
        if delta > 0:
            message = (
                f"You lean on the {degree} more than the reference "
                f"({target_pct:.0f}% vs {ref_pct:.0f}% of tonal energy). "
                f"Move some {degree} notes to a neighbouring chord tone."
            )
        else:
            message = (
                f"The reference uses the {degree} more than you do "
                f"({ref_pct:.0f}% vs {target_pct:.0f}%). "
                f"Leaning into the {degree} would move you toward its sound."
            )
        out.append(NoteSuggestion(
            kind="degree",
            severity=severity,
            message=message,
            detail={
                "degree": degree,
                "degree_index": index,
                "target_share": round(target.degree_weights[index], 4),
                "reference_share": round(reference.degree_weights[index], 4),
                "delta": delta,
            },
        ))
        if len([s for s in out if s.kind == "degree"]) >= 4:
            break

    # 4. Stray notes, with timestamps so they can actually be found.
    if target.out_of_key_notes:
        worst = sorted(
            target.out_of_key_notes, key=lambda n: abs(n.cents_away)
        )[:6]
        listed = ", ".join(
            f"{n.detected_note} at {_timecode(n.start_seconds)} → {n.nearest_in_key_note}"
            for n in worst
        )
        total = len(target.out_of_key_notes)
        out.append(NoteSuggestion(
            kind="out_of_key",
            severity="medium" if total > 2 else "low",
            message=(
                f"{total} note{'s sit' if total != 1 else ' sits'} "
                f"outside {target.key_name}: {listed}. "
                f"Some may be deliberate (blue notes, passing tones) — check before snapping."
            ),
            detail={"notes": [asdict(n) for n in worst],
                    "total": len(target.out_of_key_notes)},
        ))

    # 5. Register. Only meaningful when both tracks produced a melody.
    if target.median_midi is not None and reference.median_midi is not None:
        gap = target.median_midi - reference.median_midi
        if abs(gap) >= 6:
            octaves = gap / 12.0
            direction = "below" if gap < 0 else "above"
            out.append(NoteSuggestion(
                kind="register",
                severity="medium" if abs(gap) >= 10 else "low",
                message=(
                    f"Your melody sits {abs(octaves):.1f} octaves {direction} the "
                    f"reference ({_midi_name(target.median_midi)} vs "
                    f"{_midi_name(reference.median_midi)} median). "
                    f"That changes the weight of the vocal more than any EQ will."
                ),
                detail={
                    "target_median_midi": target.median_midi,
                    "reference_median_midi": reference.median_midi,
                    "semitones": round(gap, 2),
                },
            ))

    # 6. Honesty about confidence. A low-confidence key makes everything above
    #    provisional, and the user deserves to know that rather than trust it.
    weakest = min(target.key_confidence, reference.key_confidence)
    if weakest < 0.5:
        which = "your track" if target.key_confidence <= reference.key_confidence else "the reference"
        out.append(NoteSuggestion(
            kind="confidence",
            severity="medium",
            message=(
                f"Key detection on {which} is uncertain ({weakest:.0%}). "
                f"Treat these suggestions as provisional, or set the key manually. "
                f"Supplying an instrumental rather than a bare vocal helps most."
            ),
            detail={"target_confidence": target.key_confidence,
                    "reference_confidence": reference.key_confidence},
        ))
    return out


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mono(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio, dtype=np.float32)
    return a if a.ndim == 1 else np.mean(a, axis=1).astype(np.float32)


def _chroma_profile(mono: np.ndarray, sr: int, max_seconds: int = 120) -> np.ndarray:
    """Normalised pitch-class energy, index 0 = C.

    Percussion smears energy across every pitch class, so the harmonic
    component is isolated first — otherwise a busy drum track reads as
    "uses all twelve notes equally" and every comparison flattens out.
    """
    if len(mono) > sr * max_seconds:
        mono = mono[: sr * max_seconds]
    harmonic = librosa.effects.harmonic(mono)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sr)
    weights = np.mean(chroma, axis=1).astype(np.float64)
    total = float(np.sum(weights))
    if total <= 0:
        return np.full(12, 1.0 / 12.0)
    return weights / total


def _detect_notes(mono: np.ndarray, sr: int, max_seconds: int = 90) -> list[dict]:
    """Monophonic note centres from the tuning stage's own tracker.

    Shared with Pitch Polish so both read the same notes (a private copy here
    had drifted: it never split on pitch changes and lost a final held note).
    pyin is the expensive step in this module and it runs on both tracks, so
    the window is capped. Register and stray-note reporting are both
    statistical — they don't get materially better from minute four onward.
    """
    from ..voice.pitch import _segment_notes, _track_pitch

    if len(mono) > sr * max_seconds:
        mono = mono[: sr * max_seconds]
    notes = _segment_notes(*_track_pitch(mono, sr))
    return [n for n in notes if n["end"] - n["start"] >= 0.08]


def _stray_notes(notes: list[dict], tonic: int, allowed: set[int]) -> list[OutOfKeyNote]:
    out: list[OutOfKeyNote] = []
    for note in notes:
        nearest = int(round(note["midi"]))
        if (nearest - tonic) % 12 in allowed:
            continue
        # Nearest in-key pitch, searching outward so ties resolve downward
        # rather than arbitrarily.
        target = None
        for offset in range(1, 7):
            for candidate in (nearest - offset, nearest + offset):
                if (candidate - tonic) % 12 in allowed:
                    target = candidate
                    break
            if target is not None:
                break
        if target is None:
            continue
        out.append(OutOfKeyNote(
            start_seconds=round(note["start"], 3),
            end_seconds=round(note["end"], 3),
            detected_note=librosa.midi_to_note(note["midi"], unicode=False),
            detected_midi=round(note["midi"], 3),
            nearest_in_key_note=librosa.midi_to_note(target, unicode=False),
            nearest_in_key_midi=target,
            cents_away=round((target - note["midi"]) * 100.0, 1),
            confidence=round(note["confidence"], 3),
        ))
    return out


def _shortest_transpose(from_tonic: int, to_tonic: int) -> int:
    """Semitones from one tonic to another, taking the shorter direction.

    Returned in [-6, +6]: shifting a vocal up 7 semitones and down 5 land on the
    same pitch class, but one of them wrecks the register. Callers get the
    gentler move, with the alternative reported alongside it.
    """
    delta = (to_tonic - from_tonic) % 12
    return delta - 12 if delta > 6 else delta


def _midi_name(midi: float) -> str:
    if librosa is None:
        return f"MIDI {midi:.0f}"
    return librosa.midi_to_note(float(midi), unicode=False)


def _timecode(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds - minutes * 60:04.1f}"
