"""Local voice profile registry and reference-audio preparation."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def _default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "voices"


@dataclass
class VoiceProfile:
    id: str
    name: str
    reference_path: str
    duration_seconds: float
    sample_rate: int
    peak_dbfs: float
    clipping_percent: float
    provider: str = "seed-vc"
    kind: str = "instant"
    consent_confirmed: bool = True
    dataset_duration_seconds: float = 0.0
    dataset_clip_count: int = 0
    pitch_low_midi: float | None = None
    pitch_high_midi: float | None = None
    readiness_score: int = 0
    readiness_notes: list[str] | None = None
    training_status: str = "not-trained"
    training_steps: int = 0
    checkpoint_path: str | None = None
    config_path: str | None = None
    paired_calibration_count: int = 0
    paired_calibration_seconds: float = 0.0

    def public_dict(self) -> dict:
        data = asdict(self)
        for private_path in ("reference_path", "checkpoint_path", "config_path"):
            data.pop(private_path, None)
        return data


class VoiceProfileStore:
    """Stores voice references under the current Windows user's local data."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[VoiceProfile]:
        profiles = []
        for metadata in sorted(self.root.glob("*/profile.json")):
            try:
                profiles.append(VoiceProfile(**json.loads(metadata.read_text("utf-8"))))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return profiles

    def get(self, profile_id: str) -> VoiceProfile:
        profile_dir = self._profile_dir(profile_id)
        metadata = profile_dir / "profile.json"
        if not metadata.exists():
            raise FileNotFoundError(f"Unknown voice profile: {profile_id}")
        return VoiceProfile(**json.loads(metadata.read_text("utf-8")))

    def create(self, name: str, source_path: str, consent_confirmed: bool) -> VoiceProfile:
        if not consent_confirmed:
            raise ValueError("You must confirm that this is your voice or you have permission.")
        clean_name = re.sub(r"[^A-Za-z0-9 ._-]+", "", name).strip()[:64]
        if not clean_name:
            raise ValueError("Voice profile name is required.")

        audio, sr = sf.read(source_path, always_2d=True, dtype="float32")
        prepared, stats = prepare_reference(audio, sr)
        profile_id = uuid.uuid4().hex[:12]
        profile_dir = self.root / profile_id
        profile_dir.mkdir(parents=True, exist_ok=False)
        reference_path = profile_dir / "reference.wav"
        sf.write(reference_path, prepared, 44100, subtype="PCM_24")

        profile = VoiceProfile(
            id=profile_id,
            name=clean_name,
            reference_path=str(reference_path),
            duration_seconds=stats["duration_seconds"],
            sample_rate=44100,
            peak_dbfs=stats["peak_dbfs"],
            clipping_percent=stats["clipping_percent"],
            consent_confirmed=True,
        )
        (profile_dir / "profile.json").write_text(
            json.dumps(asdict(profile), indent=2), encoding="utf-8"
        )
        return profile

    def add_recordings(self, profile_id: str, source_paths: list[str]) -> VoiceProfile:
        """Prepare long recordings into Seed-VC-compatible 1–20 second clips."""
        profile = self.get(profile_id)
        dataset_dir = self._profile_dir(profile_id) / "dataset"
        dataset_dir.mkdir(exist_ok=True)
        next_index = len(list(dataset_dir.glob("clip_*.wav")))

        for source_path in source_paths:
            audio, sr = sf.read(source_path, always_2d=True, dtype="float32")
            mono, clipping = _prepare_dataset_audio(audio, sr)
            if clipping > 0.1:
                raise ValueError(
                    f"{Path(source_path).name} is clipping ({clipping:.2f}%). "
                    "Remove it and record at a lower level."
                )
            for clip in _segment_voice(mono, 44100):
                next_index += 1
                sf.write(
                    dataset_dir / f"clip_{next_index:05d}.wav",
                    clip,
                    44100,
                    subtype="PCM_24",
                )

        if next_index == 0:
            raise ValueError("No usable 1–20 second vocal phrases were found.")
        return self.refresh_analysis(profile_id)

    def refresh_analysis(self, profile_id: str) -> VoiceProfile:
        profile = self.get(profile_id)
        dataset_dir = self._profile_dir(profile_id) / "dataset"
        clips = sorted(dataset_dir.glob("clip_*.wav"))
        stats = analyse_dataset(clips)
        profile.dataset_duration_seconds = stats["duration_seconds"]
        profile.dataset_clip_count = stats["clip_count"]
        profile.pitch_low_midi = stats["pitch_low_midi"]
        profile.pitch_high_midi = stats["pitch_high_midi"]
        profile.readiness_score = stats["readiness_score"]
        profile.readiness_notes = stats["readiness_notes"]
        if clips and profile.kind == "instant":
            profile.kind = "studio-dataset"
        reports = list((self._profile_dir(profile_id) / "paired").glob("*/calibration.json"))
        paired_seconds = 0.0
        for report_path in reports:
            try:
                paired_seconds += float(
                    json.loads(report_path.read_text("utf-8")).get("usable_singer_seconds", 0)
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        profile.paired_calibration_count = len(reports)
        profile.paired_calibration_seconds = round(paired_seconds, 2)
        self.save(profile)
        return profile

    def mark_training(
        self,
        profile_id: str,
        *,
        status: str,
        steps: int | None = None,
        checkpoint_path: str | None = None,
        config_path: str | None = None,
    ) -> VoiceProfile:
        profile = self.get(profile_id)
        profile.training_status = status
        if steps is not None:
            profile.training_steps = steps
        if checkpoint_path is not None:
            profile.checkpoint_path = checkpoint_path
        if config_path is not None:
            profile.config_path = config_path
        if status == "trained":
            profile.kind = "studio-trained"
        self.save(profile)
        return profile

    def dataset_dir(self, profile_id: str) -> Path:
        self.get(profile_id)
        return self._profile_dir(profile_id) / "dataset"

    def save(self, profile: VoiceProfile) -> None:
        profile_dir = self._profile_dir(profile.id)
        (profile_dir / "profile.json").write_text(
            json.dumps(asdict(profile), indent=2), encoding="utf-8"
        )

    def delete(self, profile_id: str) -> None:
        profile_dir = self._profile_dir(profile_id)
        if not profile_dir.exists():
            raise FileNotFoundError(f"Unknown voice profile: {profile_id}")
        shutil.rmtree(profile_dir)

    def _profile_dir(self, profile_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{12}", profile_id):
            raise FileNotFoundError(f"Unknown voice profile: {profile_id}")
        return self.root / profile_id


def prepare_reference(audio: np.ndarray, sr: int) -> tuple[np.ndarray, dict]:
    """Validate and prepare a 3–30 second dry, monophonic voice reference."""
    if sr < 16000:
        raise ValueError("Reference audio must be at least 16 kHz.")
    if audio.size == 0:
        raise ValueError("Reference audio is empty.")

    mono = np.mean(audio, axis=1).astype(np.float32)
    peak = float(np.max(np.abs(mono)))
    clipping = float(np.mean(np.abs(mono) >= 0.999) * 100.0)
    if peak < 1e-4:
        raise ValueError("Reference audio is effectively silent.")
    if clipping > 0.1:
        raise ValueError(
            f"Reference audio is clipping ({clipping:.2f}% of samples). Record it lower."
        )

    # Trim only leading/trailing room tone; preserve breaths and internal rests.
    threshold = max(peak * 0.01, 10 ** (-55 / 20))
    active = np.flatnonzero(np.abs(mono) >= threshold)
    if active.size:
        pad = int(sr * 0.1)
        start = max(0, int(active[0]) - pad)
        stop = min(len(mono), int(active[-1]) + pad + 1)
        mono = mono[start:stop]

    duration = len(mono) / sr
    if duration < 3.0:
        raise ValueError("Use at least 3 seconds of clean solo singing.")
    if duration > 30.0:
        # Seed-VC's reference prompt is intentionally short. A trained profile
        # can use longer datasets later; instant profiles retain the first 30 s.
        mono = mono[: int(sr * 30.0)]
        duration = 30.0

    if sr != 44100:
        from math import gcd

        common = gcd(sr, 44100)
        mono = resample_poly(mono, 44100 // common, sr // common).astype(np.float32)

    # Keep natural dynamics while providing healthy inference level.
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    target_rms = 10 ** (-20 / 20)
    gain = min(target_rms / max(rms, 1e-9), (10 ** (-3 / 20)) / max(peak, 1e-9))
    mono = np.clip(mono * np.float32(gain), -1.0, 1.0)
    final_peak = float(np.max(np.abs(mono)))
    stats = {
        "duration_seconds": round(len(mono) / 44100, 2),
        "peak_dbfs": round(20 * np.log10(max(final_peak, 1e-9)), 2),
        "clipping_percent": round(clipping, 4),
    }
    return mono[:, np.newaxis], stats


def _prepare_dataset_audio(audio: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    if sr < 16000 or audio.size == 0:
        raise ValueError("Dataset audio must be non-empty and at least 16 kHz.")
    mono = np.mean(audio, axis=1).astype(np.float32)
    clipping = float(np.mean(np.abs(mono) >= 0.999) * 100.0)
    if sr != 44100:
        from math import gcd

        common = gcd(sr, 44100)
        mono = resample_poly(mono, 44100 // common, sr // common).astype(np.float32)
    peak = float(np.max(np.abs(mono)))
    if peak < 1e-4:
        raise ValueError("A dataset recording is effectively silent.")
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    gain = min((10 ** (-22 / 20)) / max(rms, 1e-9), (10 ** (-3 / 20)) / peak)
    return np.clip(mono * np.float32(gain), -1.0, 1.0), clipping


def _segment_voice(
    audio: np.ndarray,
    sr: int,
    min_seconds: float = 1.2,
    max_seconds: float = 20.0,
) -> list[np.ndarray]:
    """Split long recordings at quiet passages into training-ready phrases."""
    frame = int(sr * 0.04)
    hop = int(sr * 0.02)
    if len(audio) < int(sr * min_seconds):
        return []
    rms = np.array([
        np.sqrt(np.mean(audio[i:i + frame].astype(np.float64) ** 2))
        for i in range(0, max(len(audio) - frame + 1, 1), hop)
    ])
    threshold = max(
        min(float(np.percentile(rms, 25)) * 1.5, float(np.max(rms)) * 0.5),
        10 ** (-48 / 20),
    )
    active = rms >= threshold
    # Bridge pauses shorter than 350 ms so words are not chopped apart.
    bridge = max(1, int(0.35 / (hop / sr)))
    active = np.convolve(active.astype(np.int8), np.ones(bridge), mode="same") > 0
    indices = np.flatnonzero(active)
    if indices.size == 0:
        return []

    intervals = []
    start = prev = int(indices[0])
    for index in indices[1:]:
        index = int(index)
        if index > prev + 1:
            intervals.append((start * hop, min(len(audio), prev * hop + frame)))
            start = index
        prev = index
    intervals.append((start * hop, min(len(audio), prev * hop + frame)))

    clips = []
    pad = int(sr * 0.08)
    max_samples = int(sr * max_seconds)
    min_samples = int(sr * min_seconds)
    for start, stop in intervals:
        start, stop = max(0, start - pad), min(len(audio), stop + pad)
        while stop - start > max_samples:
            split = start + max_samples
            # Look for the quietest 500 ms around the desired split.
            radius = int(sr * 0.25)
            lo, hi = max(start + min_samples, split - radius), min(stop, split + radius)
            if hi > lo:
                window = np.abs(audio[lo:hi])
                split = lo + int(np.argmin(window))
            if split - start >= min_samples:
                clips.append(audio[start:split, np.newaxis])
            start = split
        if stop - start >= min_samples:
            clips.append(audio[start:stop, np.newaxis])
    return clips


def analyse_dataset(clips: list[Path]) -> dict:
    duration = 0.0
    pitches = []
    for path in clips:
        audio, sr = sf.read(path, always_2d=True, dtype="float32")
        duration += len(audio) / sr
        try:
            import librosa

            mono = audio[:, 0]
            if len(mono) > sr * 12:
                mono = mono[: sr * 12]
            y = librosa.resample(mono, orig_sr=sr, target_sr=22050)
            f0, voiced, _ = librosa.pyin(
                y,
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
                sr=22050,
                frame_length=2048,
            )
            valid = f0[np.isfinite(f0) & voiced]
            if valid.size:
                pitches.extend(librosa.hz_to_midi(valid[::4]).tolist())
        except Exception:
            continue

    low = round(float(np.percentile(pitches, 5)), 1) if pitches else None
    high = round(float(np.percentile(pitches, 95)), 1) if pitches else None
    pitch_span = (high - low) if low is not None and high is not None else 0.0
    notes = []
    if duration < 600:
        notes.append("Record at least 10 minutes before training.")
    elif duration < 1800:
        notes.append("30–45 minutes is recommended for a full Studio Voice.")
    if len(clips) < 40:
        notes.append("Add more separate phrases and articulations.")
    if pitch_span < 18:
        notes.append("Add low, middle, and high-register singing.")

    duration_score = min(duration / 1800, 1.0) * 55
    clip_score = min(len(clips) / 80, 1.0) * 20
    pitch_score = min(pitch_span / 24, 1.0) * 25
    return {
        "duration_seconds": round(duration, 2),
        "clip_count": len(clips),
        "pitch_low_midi": low,
        "pitch_high_midi": high,
        "readiness_score": int(round(duration_score + clip_score + pitch_score)),
        "readiness_notes": notes,
    }
