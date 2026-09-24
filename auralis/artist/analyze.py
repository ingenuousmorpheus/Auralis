"""Musical analysis of one catalog song: the raw material for Artist DNA.

Given a stereo mix and (when the song is a stem set) its separated stems, this
produces an inspectable description of the song: tempo, key, bar-level energy,
section structure, chord progression, rhythm, vocal melody range and phrasing,
and production balance.

Everything is deterministic DSP (librosa / numpy). No model, no LLM. Every
estimate that can be wrong in a musically predictable way (tempo octave,
section roles, chords) carries a confidence or is marked as a guess, because
Artist DNA is supposed to be explainable, not mysterious.

Stems make the analysis much better, and are used when present:
  drums stem  → beat tracking and rhythm (no bleed from pads or vocals)
  lead vocal  → melody range, phrasing, intervals
  bass + harmonic stems (no drums, no vocals) → key and chords
"""
from __future__ import annotations

import numpy as np

try:
    import librosa
except ImportError:  # keeps the module importable for docs without audio deps
    librosa = None

from ..engine.analysis import BAND_EDGES_HZ
from ..engine.loudness import measure
from ..voice.pitch import KEY_NAMES, detect_key

ANALYSIS_VERSION = 3   # 2: mix-only songs segmented by repetition
                       # 3: regression tempo, near-silent stems ignored
SR = 22050          # analysis rate for everything except loudness/width
HOP = 512

# A stem this far below the loudest stem is bleed or an empty export, not a part.
SILENT_STEM_DB = 30.0
MIN_VOICED_SHARE = 0.05

# Tempo is folded into this range. Most beat trackers lock onto double time for
# slow grooves (an 86 BPM R&B song reads as 172). The alternates are reported.
TEMPO_RANGE = (65.0, 145.0)

ROMAN = ["I", "♭II", "II", "♭III", "III", "IV", "♯IV", "V", "♭VI", "VI", "♭VII", "VII"]


# ── Public API ─────────────────────────────────────────────────────────────

def analyse_song(
    mix: np.ndarray,
    sr: int,
    stems: dict[str, np.ndarray] | None = None,
    progress=None,
) -> dict:
    """Analyse one song.

    ``mix`` is (samples, channels) float32 at ``sr``. ``stems`` maps a role
    (``lead_vocal``, ``backing_vocal``, ``drums``, ``bass``, ``harmonic``,
    ``other``) to a mono float32 array at ``sr``; several stems of one role
    should be summed by the caller.
    """
    if librosa is None:
        raise RuntimeError("librosa is required for catalog analysis")
    stems, ignored = _audible_stems(stems or {})

    def report(stage, pct):
        if progress:
            progress(stage, pct)

    mix = _as_2d(mix)
    if mix.shape[0] < sr * 8:
        raise ValueError("Song is shorter than 8 seconds.")

    report("loudness", 5)
    result: dict = {"analysis_version": ANALYSIS_VERSION, "stems_ignored": ignored}
    result["global"] = _global_stats(mix, sr)
    had_stems = bool(stems) or bool(ignored)

    mono = _to_rate(mix.mean(axis=1), sr)
    drums = _to_rate(stems["drums"], sr) if "drums" in stems else None
    harmonic_parts = [stems[r] for r in ("bass", "harmonic", "other") if r in stems]
    harmonic_src = _to_rate(np.sum(_pad(harmonic_parts), axis=0), sr) if harmonic_parts else None
    bass = _to_rate(stems["bass"], sr) if "bass" in stems else None
    lead = stems.get("lead_vocal")
    if lead is None:
        lead = stems.get("vocal")

    report("tempo and beats", 15)
    tempo = _tempo_and_beats(drums if drums is not None else mono)
    result["tempo"] = tempo["summary"]
    beats = tempo["beats"]

    report("bars", 30)
    downbeat_phase = _downbeat_phase(beats, drums if drums is not None else mono,
                                     bass if bass is not None else None)
    bars = _bar_frames(beats, downbeat_phase, n_frames=_n_frames(mono))
    result["tempo"]["downbeat_phase"] = int(downbeat_phase)
    result["tempo"]["bar_count"] = len(bars) - 1
    bar_times = librosa.frames_to_time(bars, sr=SR, hop_length=HOP)

    report("key", 40)
    key_source = harmonic_src if harmonic_src is not None else mono
    key = detect_key(key_source, SR, source="stems" if harmonic_src is not None else "mix")
    result["key"] = {"name": key.name, "tonic": key.tonic, "mode": key.mode,
                     "confidence": key.confidence, "source": key.source}

    report("energy", 50)
    energy = _bar_energy(mono, bars)
    result["energy"] = {"per_bar": [round(float(e), 3) for e in energy],
                        "mean": round(float(np.mean(energy)), 3) if len(energy) else 0.0}

    report("chords", 58)
    chroma_src = harmonic_src if harmonic_src is not None else librosa.effects.harmonic(mono)
    result["harmony"] = _harmony(chroma_src, bass, beats, bars, key.tonic)

    report("structure", 72)
    stems22 = {role: _to_rate(stems[role], sr) for role in _ARRANGEMENT_ROLES if role in stems}
    result["structure"] = _structure(mono, bars, bar_times, energy, stems22)

    report("rhythm", 82)
    result["rhythm"] = _rhythm(drums if drums is not None else mono, beats,
                               from_stem=drums is not None)

    if lead is not None:
        report("vocal melody", 88)
        result["melody"] = _melody(_to_rate(lead, sr, target=16000), tempo["summary"]["bpm"])
    else:
        result["melody"] = None

    # Whether a usable vocal melody exists. Only knowable from stems: a KITS
    # folder with no vocal stem, or a type-beat whose "Lead Vocals" is bleed,
    # both say False here even though the finished song may have vocals.
    result["global"]["vocal_melody_found"] = (result["melody"] is not None) if had_stems else None

    report("production", 96)
    result["production"] = _production(mix, sr, stems)
    report("done", 100)
    return result


# ── Global / production ────────────────────────────────────────────────────

def _global_stats(mix: np.ndarray, sr: int) -> dict:
    stats = measure(mix, sr)
    mono = mix.mean(axis=1)
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    return {
        "duration_seconds": round(mix.shape[0] / sr, 2),
        "sample_rate": int(sr),
        "channels": int(mix.shape[1]),
        "integrated_lufs": round(float(stats.integrated_lufs), 1),
        "true_peak_db": round(float(stats.true_peak_db), 2),
        "loudness_range_lu": _loudness_range(mix, sr),
        "crest_factor_db": round(20 * np.log10(max(peak, 1e-9) / max(rms, 1e-9)), 1),
        "stereo_width": _stereo_width(mix),
    }


def _loudness_range(mix: np.ndarray, sr: int) -> float | None:
    """EBU-style LRA approximation: spread of 3 s short-term loudness (10th–95th pct)."""
    try:
        import pyloudnorm as pyln
    except ImportError:
        return None
    meter = pyln.Meter(sr)
    window, hop = int(sr * 3), int(sr * 1)
    values = []
    for start in range(0, max(mix.shape[0] - window, 1), hop):
        block = mix[start:start + window].astype(np.float64)
        if block.shape[0] < window:
            break
        loud = meter.integrated_loudness(block)
        if np.isfinite(loud) and loud > -70:
            values.append(loud)
    if len(values) < 4:
        return None
    values = np.array(values)
    values = values[values > np.max(values) - 20]      # relative gate
    return round(float(np.percentile(values, 95) - np.percentile(values, 10)), 1)


def _stereo_width(mix: np.ndarray) -> float:
    """Side/mid RMS ratio: 0 = mono, ~0.3 typical, >0.6 very wide."""
    if mix.shape[1] < 2:
        return 0.0
    mid = 0.5 * (mix[:, 0] + mix[:, 1])
    side = 0.5 * (mix[:, 0] - mix[:, 1])
    return round(float(np.sqrt(np.mean(side ** 2)) / max(np.sqrt(np.mean(mid ** 2)), 1e-9)), 3)


def _production(mix: np.ndarray, sr: int, stems: dict) -> dict:
    mono = _to_rate(mix.mean(axis=1), sr)
    spectrum = np.abs(librosa.stft(mono, n_fft=4096, hop_length=2048)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=4096)
    total = float(spectrum.sum()) + 1e-12
    bands = []
    for lo, hi in zip(BAND_EDGES_HZ[:-1], BAND_EDGES_HZ[1:]):
        mask = (freqs >= lo) & (freqs < min(hi, SR / 2))
        bands.append(round(float(spectrum[mask].sum()) / total, 4))
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=np.sqrt(spectrum), sr=SR)))
    out = {
        "band_energy": bands,                         # 8 bands, see engine.analysis
        "band_edges_hz": BAND_EDGES_HZ,
        "spectral_centroid_hz": round(centroid, 1),
        "sub_ratio": round(bands[0], 4),               # < 100 Hz
        "low_ratio": round(bands[0] + bands[1], 4),    # < 250 Hz
        "instrumentation": None,
        "vocal_to_music_db": None,
    }
    if stems:
        levels = {role: _rms_db(audio) for role, audio in stems.items()}
        loudest = max(levels.values())
        out["instrumentation"] = {
            role: round(level - loudest, 1) for role, level in
            sorted(levels.items(), key=lambda item: -item[1])
        }
        vocal_roles = [r for r in ("lead_vocal", "vocal", "backing_vocal") if r in stems]
        music_roles = [r for r in stems if r not in vocal_roles]
        if vocal_roles and music_roles:
            vocal = np.sum(_pad([stems[r] for r in vocal_roles]), axis=0)
            music = np.sum(_pad([stems[r] for r in music_roles]), axis=0)
            out["vocal_to_music_db"] = round(_rms_db(vocal) - _rms_db(music), 1)
    return out


# ── Tempo, beats, bars ─────────────────────────────────────────────────────

def _tempo_and_beats(audio: np.ndarray) -> dict:
    onset = librosa.onset.onset_strength(y=audio, sr=SR, hop_length=HOP)
    raw_bpm, beats = librosa.beat.beat_track(onset_envelope=onset, sr=SR, hop_length=HOP,
                                             start_bpm=100.0, units="frames")
    raw_bpm = float(np.atleast_1d(raw_bpm)[0])
    bpm = raw_bpm
    factor = 1.0
    while bpm > TEMPO_RANGE[1]:
        bpm /= 2.0
        factor /= 2.0
    while bpm < TEMPO_RANGE[0]:
        bpm *= 2.0
        factor *= 2.0
    if factor < 1.0 and len(beats) > 2:
        step = int(round(1 / factor))
        # Keep the beat phase with the stronger onsets when dropping to half time.
        phases = [beats[p::step] for p in range(step)]
        beats = max(phases, key=lambda b: float(onset[b].sum()))
    elif factor > 1.0 and len(beats) > 1:
        mids = ((beats[:-1] + beats[1:]) // 2)
        beats = np.sort(np.concatenate([beats, mids]))

    grid_bpm = bpm
    beat_times = librosa.frames_to_time(beats, sr=SR, hop_length=HOP)
    if len(beat_times) >= 16:
        # The tracker's tempo is quantised to its frame rate (~5 BPM steps at
        # 120). A line through all beat times recovers the real tempo.
        lo, hi = int(len(beat_times) * 0.1), int(len(beat_times) * 0.9)
        slope = float(np.polyfit(np.arange(lo, hi), beat_times[lo:hi], 1)[0])
        if slope > 0 and abs(60.0 / slope - grid_bpm) < grid_bpm * 0.08:
            bpm = 60.0 / slope
    intervals = np.diff(beat_times)
    stability = float(1.0 - np.clip(np.std(intervals) / max(np.mean(intervals), 1e-9), 0, 1)) \
        if len(intervals) > 4 else 0.0
    # Pulse clarity: how much onset energy lands on the tracked beats.
    on_beat = float(onset[beats].mean()) if len(beats) else 0.0
    clarity = float(np.clip(on_beat / max(float(onset.mean()), 1e-9) / 3.0, 0, 1))
    return {
        "beats": np.asarray(beats, dtype=int),
        "summary": {
            "bpm": round(bpm, 1),
            "grid_bpm": round(grid_bpm, 1),
            "raw_tracker_bpm": round(raw_bpm, 1),
            "alternates": [round(bpm / 2, 1), round(bpm * 2, 1)],
            "octave_folded": factor != 1.0,
            "stability": round(stability, 3),
            "pulse_clarity": round(clarity, 3),
            "beat_count": int(len(beats)),
        },
    }


def _downbeat_phase(beats, audio, bass) -> int:
    """Pick which of every 4 beats starts the bar: the phase with the most low-end onset."""
    if len(beats) < 8:
        return 0
    source = bass if bass is not None else audio
    low = librosa.onset.onset_strength(y=source, sr=SR, hop_length=HOP, fmax=200.0,
                                       n_mels=32)
    scores = [float(low[beats[p::4]].mean()) for p in range(4)]
    return int(np.argmax(scores))


def _bar_frames(beats, phase: int, n_frames: int) -> np.ndarray:
    downbeats = np.asarray(beats[phase::4], dtype=int)
    if len(downbeats) < 2:
        return np.array([0, n_frames])
    return np.concatenate([downbeats, [min(int(downbeats[-1] + np.median(np.diff(downbeats))),
                                           n_frames)]])


# ── Energy ─────────────────────────────────────────────────────────────────

def _bar_energy(mono: np.ndarray, bars: np.ndarray) -> np.ndarray:
    rms = librosa.feature.rms(y=mono, frame_length=2048, hop_length=HOP)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    per_bar = np.array([db[a:b].mean() if b > a else db[min(a, len(db) - 1)]
                        for a, b in zip(bars[:-1], bars[1:])])
    if per_bar.size == 0:
        return per_bar
    lo, hi = np.percentile(per_bar, 5), np.percentile(per_bar, 95)
    return np.clip((per_bar - lo) / max(hi - lo, 1e-6), 0, 1)


# ── Harmony ────────────────────────────────────────────────────────────────

def _chord_templates():
    names, templates = [], []
    for root in range(12):
        for quality, intervals in (("maj", (0, 4, 7)), ("min", (0, 3, 7))):
            t = np.zeros(12)
            t[[(root + i) % 12 for i in intervals]] = 1.0
            t[root] += 0.5                                  # root emphasis
            templates.append(t / np.linalg.norm(t))
            names.append((root, quality))
    return names, np.array(templates)


def _harmony(audio, bass, beats, bars, tonic: int) -> dict:
    chroma = librosa.feature.chroma_cqt(y=audio, sr=SR, hop_length=HOP)
    if bass is not None:
        bass_chroma = librosa.feature.chroma_cqt(y=bass, sr=SR, hop_length=HOP,
                                                 fmin=librosa.note_to_hz("C1"), n_octaves=3)
        n = min(chroma.shape[1], bass_chroma.shape[1])
        chroma = chroma[:, :n] + 0.6 * bass_chroma[:, :n]
    names, templates = _chord_templates()

    # Half-bar resolution: most pop/R&B harmony moves at most twice per bar.
    edges = []
    for a, b in zip(bars[:-1], bars[1:]):
        edges.extend([a, (a + b) // 2])
    edges.append(bars[-1])
    edges = np.clip(np.asarray(edges, dtype=int), 0, chroma.shape[1])
    labels, strengths = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            labels.append(None)
            strengths.append(0.0)
            continue
        vec = chroma[:, a:b].mean(axis=1)
        norm = np.linalg.norm(vec)
        if norm < 1e-6 or vec.max() < 0.05:
            labels.append(None)
            strengths.append(0.0)
            continue
        scores = templates @ (vec / norm)
        best = int(np.argmax(scores))
        labels.append(names[best])
        strengths.append(float(scores[best]))

    def name(chord):
        if chord is None:
            return "N"
        root, quality = chord
        return KEY_NAMES[root] + ("m" if quality == "min" else "")

    def roman(chord):
        if chord is None:
            return "N"
        root, quality = chord
        numeral = ROMAN[(root - tonic) % 12]
        return numeral.lower() if quality == "min" else numeral

    half_bars = [name(c) for c in labels]
    per_bar = [half_bars[i] for i in range(0, len(half_bars), 2)]
    romans_per_bar = [roman(labels[i]) for i in range(0, len(labels), 2)]
    changes = sum(1 for x, y in zip(half_bars[:-1], half_bars[1:]) if x != y and "N" not in (x, y))
    bar_count = max(len(per_bar), 1)

    vocab: dict[str, int] = {}
    for r in romans_per_bar:
        if r != "N":
            vocab[r] = vocab.get(r, 0) + 1
    total = sum(vocab.values()) or 1
    progressions: dict[tuple, int] = {}
    for i in range(0, len(romans_per_bar) - 3):
        window = tuple(romans_per_bar[i:i + 4])
        if "N" in window or len(set(window)) < 2:
            continue
        progressions[window] = progressions.get(window, 0) + 1
    top = sorted(progressions.items(), key=lambda kv: -kv[1])[:5]
    diatonic_major = {"I", "ii", "iii", "IV", "V", "vi"}
    diatonic_minor = {"i", "♭III", "iv", "v", "V", "♭VI", "♭VII"}
    diatonic = sum(c for r, c in vocab.items() if r in diatonic_major | diatonic_minor)
    return {
        "chords_per_bar": per_bar,
        "roman_per_bar": romans_per_bar,
        "changes_per_bar": round(changes / bar_count, 2),
        "vocabulary": {r: round(c / total, 3) for r, c in sorted(vocab.items(), key=lambda kv: -kv[1])},
        "top_progressions": [{"progression": list(p), "count": c} for p, c in top],
        "diatonic_share": round(diatonic / total, 3),
        "mean_fit": round(float(np.mean([s for s in strengths if s > 0])) if any(strengths) else 0.0, 3),
    }


# ── Structure ──────────────────────────────────────────────────────────────
#
# Sections are found from the ARRANGEMENT (who is playing, how loud, what
# timbre), not from harmony alone. R&B and pop often loop one 4-bar chord cycle
# through verse and chorus, so chord-based repetition finds the loop, not the
# song form. Stems make this direct: per-bar activity of lead vocal, backing
# vocals, drums, bass and music says "chorus" (backing vocals in, full drums)
# or "break" (lead vocal out) far more reliably than a mix can.

_ARRANGEMENT_ROLES = ("lead_vocal", "vocal", "backing_vocal", "drums", "bass", "harmonic", "other")

_SHORT = {"intro": "Intro", "verse": "V", "pre-chorus": "PC", "chorus": "C", "bridge": "B",
          "instrumental": "Inst", "outro": "Outro", "section": "S"}


def _structure(mono, bars, bar_times, energy, stems22: dict) -> dict:
    n_bars = len(bars) - 1
    if n_bars < 8:
        return {"sections": [], "form": "", "roles_form": "", "note": "too short to segment"}
    activity, columns = _arrangement(mono, bars, stems22)
    mfcc = librosa.feature.mfcc(y=mono, sr=SR, hop_length=HOP, n_mfcc=13)[1:]
    b = np.clip(bars, 0, mfcc.shape[1] - 1)
    timbre = np.stack([mfcc[:, x:y].mean(axis=1) if y > x else mfcc[:, x]
                       for x, y in zip(b[:-1], b[1:])], axis=0)
    timbre = (timbre - timbre.mean(0)) / (timbre.std(0) + 1e-9) / 4
    if stems22:
        spans, labels = _segments_by_arrangement(np.hstack([2.0 * activity, timbre]))
    else:
        # A loudly mastered full mix has nearly flat arrangement energy, so
        # sections are told apart by what REPEATS: chroma + timbre per bar.
        spans, labels = _segments_by_repetition(mono, bars, energy, timbre)

    # Neighbours that sound alike are one section with a small internal change.
    merged_spans, merged_labels = [], []
    for span, label in zip(spans, labels):
        if merged_labels and merged_labels[-1] == label:
            merged_spans[-1] = (merged_spans[-1][0], span[1])
        else:
            merged_spans.append(span)
            merged_labels.append(label)
    # Re-letter in order of first appearance so forms read A B A C...
    order: dict[int, int] = {}
    for label in merged_labels:
        order.setdefault(label, len(order))
    spans, labels = merged_spans, [order[label] for label in merged_labels]

    sections = []
    for (a, e), label in zip(spans, labels):
        act = activity[a:e].mean(axis=0)
        sections.append({
            "start_bar": int(a), "bars": int(e - a),
            "start_seconds": round(float(bar_times[a]), 2),
            "end_seconds": round(float(bar_times[min(e, len(bar_times) - 1)]), 2),
            "label": chr(ord("A") + label) if label < 26 else f"Z{label}",
            "energy": round(float(np.mean(energy[a:e])), 3) if len(energy) else 0.0,
            "arrangement": {c: round(float(x), 2) for c, x in zip(columns, act)},
        })
    _guess_roles(sections, has_stems=bool(stems22))
    return {
        "sections": sections,
        "form": " ".join(s["label"] for s in sections),
        "roles_form": " ".join(_collapse([_SHORT.get(s["role_guess"], "?") for s in sections])),
        "method": "stem arrangement" if stems22 else "mix repetition",
        "roles_are_guesses": True,
    }


def _checkerboard_boundaries(sim: np.ndarray, extra: np.ndarray | None = None) -> list[int]:
    """Section boundaries (bar indices, incl. 0 and n) from a bar similarity matrix."""
    n = sim.shape[0]
    k = 4
    kernel = np.kron(np.array([[1, -1], [-1, 1]]), np.ones((k, k)))
    padded = np.pad(sim, k, mode="edge")
    novelty = np.array([np.sum(padded[i:i + 2 * k, i:i + 2 * k] * kernel) for i in range(n)])
    novelty = (novelty - novelty.min()) / (np.ptp(novelty) + 1e-9)
    if extra is not None:
        novelty = novelty + extra
    peaks = [i for i in range(2, n - 2)
             if novelty[i] == novelty[max(0, i - 3):i + 4].max()
             and novelty[i] > novelty.mean() + 0.25 * novelty.std()]
    boundaries = [0]
    for p in sorted(peaks, key=lambda i: -novelty[i]):
        if all(abs(p - q) >= 4 for q in boundaries) and n - p >= 2:
            boundaries.append(p)
    return sorted(boundaries) + [n]


def _segments_by_arrangement(features: np.ndarray) -> tuple[list, list]:
    """Stem path: sections whose arrangement + timbre look alike share a label."""
    dist = np.linalg.norm(features[:, None] - features[None], axis=2)
    sim = np.exp(-dist / (np.median(dist) + 1e-9))
    boundaries = _checkerboard_boundaries(sim)
    spans = list(zip(boundaries[:-1], boundaries[1:]))
    vectors = np.array([features[a:e].mean(axis=0) for a, e in spans])
    pairwise = np.linalg.norm(vectors[:, None] - vectors[None], axis=2)
    threshold = float(np.percentile(pairwise[np.triu_indices(len(spans), 1)], 30)) \
        if len(spans) > 2 else 0.0
    labels, prototypes = [], []
    for v in vectors:
        d = [np.linalg.norm(v - p) for p in prototypes]
        if d and min(d) <= threshold:
            labels.append(int(np.argmin(d)))
        else:
            prototypes.append(v)
            labels.append(len(prototypes) - 1)
    return spans, labels


def _segments_by_repetition(mono, bars, energy, timbre) -> tuple[list, list]:
    """Mix path: two sections share a label when they repeat bar-for-bar."""
    n = len(bars) - 1
    chroma = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(mono), sr=SR, hop_length=HOP)
    b = np.clip(bars, 0, chroma.shape[1] - 1)
    ch = np.stack([chroma[:, x:y].mean(axis=1) if y > x else chroma[:, x]
                   for x, y in zip(b[:-1], b[1:])], axis=1)
    ch /= np.linalg.norm(ch, axis=0, keepdims=True) + 1e-9
    tb = timbre.T / (np.linalg.norm(timbre.T, axis=0, keepdims=True) + 1e-9)
    ssm = 0.6 * (ch.T @ ch) + 0.4 * (tb.T @ tb)
    e = np.asarray(energy, dtype=float)
    jumps = 0.5 * np.abs(np.diff(e, prepend=e[0])) if len(e) == n else None
    boundaries = _checkerboard_boundaries(ssm, jumps)
    spans = list(zip(boundaries[:-1], boundaries[1:]))
    # "Same section" = aligned bar-by-bar similarity in the song's top 15%.
    threshold = float(np.percentile(ssm[~np.eye(n, dtype=bool)], 85))

    def aligned(a, c):
        length = min(a[1] - a[0], c[1] - c[0])
        return float(np.mean([ssm[a[0] + i, c[0] + i] for i in range(length)]))

    labels = [-1] * len(spans)
    next_label = 0
    for i, span in enumerate(spans):
        if labels[i] >= 0:
            continue
        labels[i] = next_label
        for j in range(i + 1, len(spans)):
            if labels[j] < 0 and aligned(span, spans[j]) >= threshold:
                labels[j] = next_label
        next_label += 1
    return spans, labels


def _arrangement(mono, bars, stems22: dict) -> tuple[np.ndarray, list[str]]:
    """Per-bar activity (0 = silent, 1 = its loudest) for each stem or mix band."""
    def activity(y):
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
        b = np.clip(bars, 0, len(rms) - 1)
        db = np.array([20 * np.log10(max(rms[x:z].mean() if z > x else rms[x], 1e-6))
                       for x, z in zip(b[:-1], b[1:])])
        return np.clip((db - db.max() + 40.0) / 40.0, 0.0, 1.0)

    columns, cols = [], []
    if stems22:
        for role in _ARRANGEMENT_ROLES:
            if role in stems22:
                columns.append(role)
                cols.append(activity(stems22[role]))
    else:
        harmonic, percussive = librosa.effects.hpss(mono)
        for label, y in (("harmonic_part", harmonic), ("percussive_part", percussive)):
            columns.append(label)
            cols.append(activity(y))
        spec = np.abs(librosa.stft(mono, hop_length=HOP))
        freqs = librosa.fft_frequencies(sr=SR)
        b = np.clip(bars, 0, spec.shape[1] - 1)
        for label, lo, hi in (("low_band", 20, 250), ("mid_band", 250, 2000), ("high_band", 2000, 11000)):
            band = spec[(freqs >= lo) & (freqs < hi)].mean(axis=0)
            db = np.array([20 * np.log10(max(band[x:z].mean() if z > x else band[x], 1e-9))
                           for x, z in zip(b[:-1], b[1:])])
            columns.append(label)
            cols.append(np.clip((db - db.max() + 40.0) / 40.0, 0.0, 1.0))
    return np.stack(cols, axis=1), columns


def _guess_roles(sections: list[dict], has_stems: bool) -> None:
    """Name sections from repetition + arrangement. Always a guess, and marked so."""
    counts: dict[str, int] = {}
    for s in sections:
        counts[s["label"]] = counts.get(s["label"], 0) + 1

    def act(s, role):
        return s["arrangement"].get(role, 0.0)

    lead_key = "lead_vocal" if any("lead_vocal" in s["arrangement"] for s in sections) else "vocal"
    has_lead = has_stems and any(lead_key in s["arrangement"] for s in sections)

    def hook_score(label):
        members = [s for s in sections if s["label"] == label]
        score = float(np.mean([s["energy"] for s in members]))
        if has_stems:
            score += 0.8 * float(np.mean([act(s, "backing_vocal") for s in members]))
            score += 0.3 * float(np.mean([act(s, "drums") for s in members]))
        return score

    repeated = [label for label, c in counts.items() if c >= 2]
    chorus = max(repeated, key=hook_score) if repeated else None
    others = [label for label in repeated if label != chorus]
    verse = max(others, key=lambda l: (counts[l], -hook_score(l))) if others else None
    first_chorus = next((i for i, s in enumerate(sections) if s["label"] == chorus), None)
    last = len(sections) - 1
    for i, s in enumerate(sections):
        silent_lead = has_lead and act(s, lead_key) < 0.2
        if i == 0 and (silent_lead or s["energy"] < 0.45) and s["bars"] <= 16:
            role = "intro"
        elif i == last and (silent_lead or s["energy"] < 0.5) and s["bars"] <= 16:
            role = "outro"
        elif silent_lead:
            role = "instrumental"
        elif s["label"] == chorus:
            role = "chorus"
        elif s["label"] == verse:
            role = "verse"
        elif i + 1 < len(sections) and sections[i + 1]["label"] == chorus and s["bars"] <= 8:
            role = "pre-chorus"
        elif first_chorus is not None and i > first_chorus and counts[s["label"]] == 1:
            role = "bridge"
        elif i == 0 and s["bars"] <= 8:
            role = "intro"
        elif i == last and s["bars"] <= 8:
            role = "outro"
        else:
            role = "section"
        s["role_guess"] = role


# ── Rhythm ─────────────────────────────────────────────────────────────────

def _rhythm(audio, beats, from_stem: bool) -> dict:
    if not from_stem:
        audio = librosa.effects.percussive(audio)
    onset = librosa.onset.onset_strength(y=audio, sr=SR, hop_length=HOP)
    onsets = librosa.onset.onset_detect(onset_envelope=onset, sr=SR, hop_length=HOP, units="frames")
    if len(beats) < 8:
        return {"source": "drums stem" if from_stem else "percussive mix", "onsets_per_beat": None}
    beat_len = float(np.median(np.diff(beats)))
    # Position of each onset within its beat, 0..1.
    idx = np.searchsorted(beats, onsets, side="right") - 1
    valid = (idx >= 0) & (idx < len(beats) - 1)
    positions = (onsets[valid] - beats[idx[valid]]) / np.maximum(np.diff(beats)[idx[valid]], 1)
    strengths = onset[onsets[valid]]
    total = float(strengths.sum()) or 1.0
    on_beat = float(strengths[(positions < 0.12) | (positions > 0.88)].sum())
    eighth_off = float(strengths[(positions >= 0.38) & (positions <= 0.72)].sum())
    sixteenth = float(strengths[((positions >= 0.12) & (positions < 0.38)) |
                                ((positions > 0.72) & (positions <= 0.88))].sum())
    offbeat_positions = positions[(positions >= 0.4) & (positions <= 0.8)]
    swing = float(np.median(offbeat_positions)) if offbeat_positions.size > 16 else None
    return {
        "source": "drums stem" if from_stem else "percussive mix",
        "onsets_per_beat": round(len(onsets) / max(len(beats), 1), 2),
        "on_beat_share": round(on_beat / total, 3),
        "eighth_offbeat_share": round(eighth_off / total, 3),
        "sixteenth_share": round(sixteenth / total, 3),
        "syncopation": round((eighth_off + sixteenth) / total, 3),
        # 0.5 = straight eighths, ~0.62-0.67 = swung / shuffled.
        "swing_position": round(swing, 3) if swing is not None else None,
        "beat_frames_median": round(beat_len, 1),
    }


# ── Melody (lead vocal stem) ───────────────────────────────────────────────

def _melody(vocal: np.ndarray, bpm: float) -> dict | None:
    sr = 16000
    if np.max(np.abs(vocal)) < 1e-3:
        return None
    hop = 320
    f0, voiced, prob = librosa.pyin(vocal, fmin=librosa.note_to_hz("C2"),
                                    fmax=librosa.note_to_hz("C6"), sr=sr,
                                    frame_length=1024, hop_length=hop, fill_na=np.nan)
    midi = librosa.hz_to_midi(f0)
    good = np.isfinite(midi) & voiced & (prob > 0.4)
    # A few voiced frames are separation bleed, not a melody worth describing.
    if good.sum() < 50 or good.mean() < MIN_VOICED_SHARE:
        return None
    frame_s = hop / sr
    values = midi[good]
    # Notes: runs of stable pitch.
    notes = []
    start = None
    for i in range(len(midi)):
        if good[i] and start is None:
            start = i
        stable = good[i] and start is not None and abs(midi[i] - np.nanmedian(midi[start:i + 1])) < 0.8
        if start is not None and (not stable or i == len(midi) - 1):
            if i - start >= 4:
                notes.append((start, i, float(np.nanmedian(midi[start:i]))))
            start = i if good[i] else None
    intervals = np.diff([round(n[2]) for n in notes]) if len(notes) > 1 else np.array([])
    intervals = intervals[np.abs(intervals) <= 12]
    # Phrases: voiced runs separated by >= 350 ms of silence.
    phrases = []
    gap_frames = int(0.35 / frame_s)
    run_start, silence = None, 0
    for i, g in enumerate(good):
        if g:
            if run_start is None:
                run_start = i
            silence = 0
        elif run_start is not None:
            silence += 1
            if silence >= gap_frames:
                phrases.append((i - silence - run_start) * frame_s)
                run_start, silence = None, 0
    if run_start is not None:
        phrases.append((len(good) - run_start) * frame_s)
    phrases = [p for p in phrases if p >= 0.5]
    beat_s = 60.0 / bpm if bpm else 0.5
    abs_int = np.abs(intervals)
    return {
        "range_low_midi": round(float(np.percentile(values, 5)), 1),
        "range_high_midi": round(float(np.percentile(values, 95)), 1),
        "range_low_note": librosa.midi_to_note(float(np.percentile(values, 5))),
        "range_high_note": librosa.midi_to_note(float(np.percentile(values, 95))),
        "median_note": librosa.midi_to_note(float(np.median(values))),
        "voiced_share": round(float(good.mean()), 3),
        "note_count": len(notes),
        "phrase_count": len(phrases),
        "phrase_seconds_median": round(float(np.median(phrases)), 2) if phrases else None,
        "phrase_beats_median": round(float(np.median(phrases)) / beat_s, 1) if phrases else None,
        "interval_profile": {
            "repeat": round(float(np.mean(abs_int == 0)), 3) if abs_int.size else None,
            "step": round(float(np.mean((abs_int >= 1) & (abs_int <= 2))), 3) if abs_int.size else None,
            "skip": round(float(np.mean((abs_int >= 3) & (abs_int <= 5))), 3) if abs_int.size else None,
            "leap": round(float(np.mean(abs_int >= 6)), 3) if abs_int.size else None,
            "rising_share": round(float(np.mean(intervals > 0)), 3) if intervals.size else None,
        },
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _audible_stems(stems: dict) -> tuple[dict, list[str]]:
    """Drop stems that are silent or bleed-only (e.g. an empty 'Lead Vocals' export)."""
    if not stems:
        return {}, []
    levels = {role: _rms_db(audio) for role, audio in stems.items()}
    loudest = max(levels.values())
    keep = {r: a for r, a in stems.items() if levels[r] >= loudest - SILENT_STEM_DB}
    return keep, sorted(r for r in stems if r not in keep)


def _collapse(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if not out or out[-1] != item:
            out.append(item)
    return out


def _as_2d(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    return audio[:, np.newaxis] if audio.ndim == 1 else audio


def _to_rate(audio: np.ndarray, sr: int, target: int = SR) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr == target:
        return audio
    return librosa.resample(audio, orig_sr=sr, target_sr=target, res_type="soxr_hq")


def _pad(arrays: list[np.ndarray]) -> np.ndarray:
    n = max(len(a) for a in arrays)
    return np.stack([np.pad(a, (0, n - len(a))) for a in arrays])


def _n_frames(mono: np.ndarray) -> int:
    return 1 + len(mono) // HOP


def _zscore(x: np.ndarray) -> np.ndarray:
    return (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-9)


def _rms_db(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.asarray(audio, dtype=np.float64) ** 2)))
    return round(20 * np.log10(max(rms, 1e-9)), 1)
