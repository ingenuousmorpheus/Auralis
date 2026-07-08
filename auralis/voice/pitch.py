"""Automatic, key-aware vocal pitch polishing with inspectable note decisions."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter
from scipy.signal import butter, sosfiltfilt

from ..engine.loudness import apply_true_peak_ceiling


KEY_NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
SCALES = {
    "major": {0, 2, 4, 5, 7, 9, 11},
    "minor": {0, 2, 3, 5, 7, 8, 10},
}
STYLES = {
    "natural": {"strength": 0.55, "max_cents": 90, "deadband": 16},
    "studio": {"strength": 0.78, "max_cents": 150, "deadband": 10},
    "modern": {"strength": 0.93, "max_cents": 220, "deadband": 6},
    "hard": {"strength": 1.0, "max_cents": 350, "deadband": 0},
}


@dataclass
class KeyEstimate:
    tonic: int
    mode: str
    name: str
    confidence: float
    source: str


@dataclass
class NoteEdit:
    start_seconds: float
    end_seconds: float
    detected_midi: float
    detected_note: str
    target_midi: int
    target_note: str
    raw_cents: float
    applied_cents: float
    confidence: float
    corrected: bool


def pitch_polish(
    vocal_path: str,
    output_path: str,
    style: str = "studio",
    instrumental_path: str | None = None,
    key_override: str | None = None,
    report_path: str | None = None,
    progress=None,
) -> dict:
    if style not in STYLES:
        raise ValueError(f"Unknown Pitch Polish style: {style}")
    vocal, sr = sf.read(vocal_path, always_2d=True, dtype="float32")
    mono = np.mean(vocal, axis=1).astype(np.float32)
    if progress:
        progress("detecting vocal notes", 12)
    times, f0, voiced_prob = _track_pitch(mono, sr)
    notes = _segment_notes(times, f0, voiced_prob)
    if len(notes) < 2:
        raise ValueError("Not enough stable pitched notes were detected.")

    if key_override and key_override != "auto":
        key = parse_key(key_override)
    else:
        key_audio = None
        key_sr = sr
        source = "vocal"
        if instrumental_path:
            key_audio, key_sr = sf.read(
                instrumental_path, always_2d=True, dtype="float32"
            )
            key_audio = np.mean(key_audio, axis=1)
            source = "instrumental"
        else:
            key_audio = mono
        key = detect_key(key_audio, key_sr, source=source)
    if progress:
        progress(f"mapping melody to {key.name}", 35)

    edits = _map_notes(notes, key, style)
    rendered = _render_edits(mono, sr, edits)
    rendered = apply_true_peak_ceiling(rendered[:, np.newaxis], sr, -1.0)
    sf.write(output_path, rendered, sr, subtype="PCM_24")

    corrected = [edit for edit in edits if edit.corrected]
    report = {
        "output_path": output_path,
        "key": asdict(key),
        "style": style,
        "notes_detected": len(edits),
        "notes_corrected": len(corrected),
        "average_correction_cents": round(
            float(np.mean([abs(e.applied_cents) for e in corrected])) if corrected else 0.0,
            2,
        ),
        "low_confidence_notes": sum(e.confidence < 0.55 for e in edits),
        "edits": [asdict(edit) for edit in edits],
    }
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    report["report_path"] = report_path
    if progress:
        progress("pitch polish complete", 98)
    return report


def detect_key(audio: np.ndarray, sr: int, source: str = "audio") -> KeyEstimate:
    mono = np.asarray(audio, dtype=np.float32)
    if mono.ndim > 1:
        mono = np.mean(mono, axis=1)
    if len(mono) > sr * 90:
        mono = mono[: sr * 90]
    harmonic = librosa.effects.harmonic(mono)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sr)
    weights = np.mean(chroma, axis=1)
    weights /= np.linalg.norm(weights) + 1e-12
    candidates = []
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = np.roll(profile, tonic)
            rotated = rotated / np.linalg.norm(rotated)
            candidates.append((float(np.dot(weights, rotated)), tonic, mode))
    candidates.sort(reverse=True)
    best, second = candidates[0], candidates[1]
    confidence = float(np.clip((best[0] - second[0]) * 8.0 + 0.35, 0.0, 1.0))
    name = f"{KEY_NAMES[best[1]]} {best[2]}"
    return KeyEstimate(best[1], best[2], name, round(confidence, 3), source)


def parse_key(value: str) -> KeyEstimate:
    normalized = value.strip().replace("#", "♯").replace("b", "♭")
    parts = normalized.split()
    if len(parts) != 2 or parts[1].lower() not in SCALES:
        raise ValueError("Key must look like 'C major' or 'F# minor'.")
    aliases = {
        "D♭": "C♯", "G♭": "F♯", "A♭": "A♭", "E♭": "E♭",
        "B♭": "B♭", "C♭": "B", "E♯": "F", "B♯": "C", "F♭": "E",
    }
    tonic_name = aliases.get(parts[0], parts[0])
    if tonic_name not in KEY_NAMES:
        raise ValueError(f"Unknown key tonic: {parts[0]}")
    tonic = KEY_NAMES.index(tonic_name)
    mode = parts[1].lower()
    return KeyEstimate(tonic, mode, f"{KEY_NAMES[tonic]} {mode}", 1.0, "manual")


def _track_pitch(audio: np.ndarray, sr: int):
    hop = 256
    f0, voiced, probability = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
        frame_length=2048,
        hop_length=hop,
        fill_na=np.nan,
    )
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop)
    probability = np.where(voiced, probability, 0.0)
    return times, f0, probability


def _segment_notes(times, f0, probability) -> list[dict]:
    midi = librosa.hz_to_midi(f0)
    smooth = median_filter(np.nan_to_num(midi, nan=-999.0), size=5)
    voiced = np.isfinite(midi) & (probability >= 0.45)
    segments = []
    start = None
    previous = None
    for index, active in enumerate(voiced):
        split = False
        if active and previous is not None and abs(smooth[index] - smooth[previous]) > 0.85:
            split = True
        if active and start is None:
            start = index
        elif (not active or split) and start is not None:
            stop = index
            if stop - start >= 5:
                values = midi[start:stop]
                probs = probability[start:stop]
                valid = np.isfinite(values)
                if np.any(valid):
                    segments.append({
                        "start": float(times[start]),
                        "end": float(times[min(stop, len(times) - 1)]),
                        "midi": float(np.median(values[valid])),
                        "confidence": float(np.mean(probs[valid])),
                    })
            start = index if active else None
        previous = index if active else previous
    if start is not None and len(midi) - start >= 5:
        valid = np.isfinite(midi[start:])
        segments.append({
            "start": float(times[start]),
            "end": float(times[-1] + (times[1] - times[0])),
            "midi": float(np.median(midi[start:][valid])),
            "confidence": float(np.mean(probability[start:][valid])),
        })
    return [segment for segment in segments if segment["end"] - segment["start"] >= 0.06]


def _map_notes(notes: list[dict], key: KeyEstimate, style: str) -> list[NoteEdit]:
    settings = STYLES[style]
    allowed = SCALES[key.mode]
    candidate_lists = []
    for note in notes:
        center = note["midi"]
        nearby = [
            midi for midi in range(int(np.floor(center)) - 2, int(np.ceil(center)) + 3)
            if (midi - key.tonic) % 12 in allowed
        ]
        candidate_lists.append(nearby or [int(round(center))])

    # Dynamic programming preserves the singer's melodic contour when two scale
    # tones are similarly plausible.
    costs = []
    paths = []
    for index, (note, candidates) in enumerate(zip(notes, candidate_lists)):
        local_costs = {}
        local_paths = {}
        for candidate in candidates:
            pitch_cost = (candidate - note["midi"]) ** 2
            if index == 0:
                local_costs[candidate] = pitch_cost
                local_paths[candidate] = [candidate]
                continue
            best_cost, best_path = None, None
            source_interval = note["midi"] - notes[index - 1]["midi"]
            for previous, previous_cost in costs[-1].items():
                target_interval = candidate - previous
                contour_cost = 0.18 * (target_interval - source_interval) ** 2
                total = previous_cost + pitch_cost + contour_cost
                if best_cost is None or total < best_cost:
                    best_cost = total
                    best_path = paths[-1][previous] + [candidate]
            local_costs[candidate] = best_cost
            local_paths[candidate] = best_path
        costs.append(local_costs)
        paths.append(local_paths)
    final_target = min(costs[-1], key=costs[-1].get)
    targets = paths[-1][final_target]

    edits = []
    for note, target in zip(notes, targets):
        raw_cents = (target - note["midi"]) * 100.0
        magnitude = abs(raw_cents)
        if magnitude <= settings["deadband"]:
            applied = 0.0
        else:
            # Lower settings leave near-correct notes alone while rescuing larger
            # misses—the useful behavior of an intelligent correction macro.
            severity = np.clip(
                (magnitude - settings["deadband"]) / max(settings["max_cents"], 1),
                0.0,
                1.0,
            )
            adaptive_strength = settings["strength"] * (0.45 + 0.55 * severity)
            if note["confidence"] < 0.55:
                adaptive_strength *= 0.45
            applied = float(
                np.clip(raw_cents * adaptive_strength, -settings["max_cents"], settings["max_cents"])
            )
        edits.append(NoteEdit(
            start_seconds=round(note["start"], 4),
            end_seconds=round(note["end"], 4),
            detected_midi=round(note["midi"], 3),
            detected_note=librosa.midi_to_note(note["midi"], unicode=False),
            target_midi=int(target),
            target_note=librosa.midi_to_note(target, unicode=False),
            raw_cents=round(raw_cents, 2),
            applied_cents=round(applied, 2),
            confidence=round(note["confidence"], 3),
            corrected=abs(applied) >= 1.0,
        ))
    return edits


def _render_edits(audio: np.ndarray, sr: int, edits: list[NoteEdit]) -> np.ndarray:
    output = audio.astype(np.float32).copy()
    pad = int(sr * 0.045)
    sos = butter(4, min(5200, sr * 0.42), btype="lowpass", fs=sr, output="sos")
    for edit in edits:
        if not edit.corrected:
            continue
        core_start = max(0, int(edit.start_seconds * sr))
        core_stop = min(len(audio), int(edit.end_seconds * sr))
        start, stop = max(0, core_start - pad), min(len(audio), core_stop + pad)
        if stop - start < 256:
            continue
        segment = audio[start:stop]
        tonal = sosfiltfilt(sos, segment).astype(np.float32)
        unpitched = segment - tonal
        shifted_tonal = librosa.effects.pitch_shift(
            tonal,
            sr=sr,
            n_steps=edit.applied_cents / 100.0,
            bins_per_octave=12,
            res_type="soxr_hq",
        ).astype(np.float32)
        shifted = shifted_tonal + unpitched
        fade_in = core_start - start
        fade_out = stop - core_stop
        envelope = np.ones(stop - start, dtype=np.float32)
        if fade_in > 0:
            envelope[:fade_in] = np.sin(np.linspace(0, np.pi / 2, fade_in)) ** 2
        if fade_out > 0:
            envelope[-fade_out:] = np.cos(np.linspace(0, np.pi / 2, fade_out)) ** 2
        output[start:stop] = segment * (1.0 - envelope) + shifted * envelope
    return output.astype(np.float32)
