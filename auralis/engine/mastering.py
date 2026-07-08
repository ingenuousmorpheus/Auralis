"""Mastering stage.

Two modes:

* **reference mode** — when a profile supplies a reference WAV, use Matchering to
  match the target's frequency response, RMS, peak and stereo width to it.
* **internal-target mode** — when no reference is bundled, apply a transparent
  chain (gentle bus glue + true-peak safety) so the tool still produces a valid
  master. This keeps Phase 1 shippable before reference libraries are curated.

In both modes the loudness stage (loudness.py) runs afterwards to hit the target
LUFS and enforce the true-peak ceiling.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import numpy as np
import soundfile as sf

from .loudness import (
    DEFAULT_TRUE_PEAK_CEILING_DB,
    measure,
    normalize_with_limiter,
)
from .profiles_loader import StyleProfile

try:
    import matchering as mg
except ImportError:  # pragma: no cover
    mg = None


@dataclass
class MasterResult:
    output_path: str
    before_lufs: float
    after_lufs: float
    before_peak_db: float
    after_peak_db: float
    profile_id: str
    mode: str  # "reference" | "internal-target"


def master_file(
    input_path: str,
    output_path: str,
    profile: StyleProfile,
    target_lufs: float | None = None,
    ceiling_db: float = DEFAULT_TRUE_PEAK_CEILING_DB,
    reference_path: str | None = None,
    progress=None,
) -> MasterResult:
    """Master ``input_path`` to ``output_path``.

    Reference resolution order (first match wins):

    1. ``reference_path`` — a track the *user* supplies at runtime (their own
       copy of a commercial song, never stored in the repo). This is the
       Ozone-style "match this song" workflow and takes priority.
    2. ``profile.reference_path`` — an optional reference bundled with a profile
       (used only if you legally curate one).
    3. internal-target mode — a transparent chain when no reference is given.

    In all cases Matchering only *analyses* the reference (frequency response,
    RMS, peak, stereo width) to retune the target. The reference's audio is
    never copied into the output.

    ``progress`` is an optional callable ``(stage: str, pct: float) -> None``.
    """
    def report(stage: str, pct: float) -> None:
        if progress:
            progress(stage, pct)

    report("analyzing", 5)
    audio, sr = sf.read(input_path, always_2d=True, dtype="float32")
    before = measure(audio, sr)

    ref = reference_path or profile.reference_path
    if ref and os.path.exists(ref) and mg is not None:
        mode = "reference"
        report("matching reference", 35)
        mastered = _matchering_master(input_path, ref)
        try:
            audio, sr = sf.read(mastered, always_2d=True, dtype="float32")
        finally:
            if os.path.exists(mastered):
                os.remove(mastered)
    else:
        mode = "internal-target"
        report("applying glue", 35)
        audio = _internal_glue(audio, sr, profile)

    tlufs = target_lufs if target_lufs is not None else profile.default_target_lufs
    report("normalizing loudness", 70)
    report("limiting", 82)
    audio = normalize_with_limiter(audio, sr, tlufs, ceiling_db)

    after = measure(audio, sr)
    sf.write(output_path, audio, sr, subtype="PCM_24")
    report("done", 100)

    return MasterResult(
        output_path=output_path,
        before_lufs=round(before.integrated_lufs, 1),
        after_lufs=round(after.integrated_lufs, 1),
        before_peak_db=round(before.true_peak_db, 2),
        after_peak_db=round(after.true_peak_db, 2),
        profile_id=profile.id,
        mode=mode,
    )


def _matchering_master(target_path: str, reference_path: str) -> str:
    """Run Matchering, returning a path to the mastered WAV."""
    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out = handle.name
    handle.close()
    mg.process(
        target=target_path,
        reference=reference_path,
        results=[mg.pcm24(out)],
    )
    return out


def _internal_glue(audio: np.ndarray, sr: int, profile: StyleProfile) -> np.ndarray:
    """Apply the profile's measurable tone, dynamics, and width targets."""
    a = audio.astype(np.float32)
    tonal = profile.targets.get("tonal_curve", "flat")
    ratio = float(profile.targets.get("compression", {}).get("bus_ratio", 1.0))

    try:
        from pedalboard import (
            Compressor,
            HighShelfFilter,
            LowShelfFilter,
            PeakFilter,
            Pedalboard,
        )

        processors = []
        if tonal == "bright":
            processors.extend([
                LowShelfFilter(cutoff_frequency_hz=180.0, gain_db=-0.6, q=0.7),
                HighShelfFilter(cutoff_frequency_hz=6500.0, gain_db=1.4, q=0.7),
            ])
        elif tonal == "warm":
            processors.extend([
                LowShelfFilter(cutoff_frequency_hz=180.0, gain_db=1.0, q=0.7),
                HighShelfFilter(cutoff_frequency_hz=8500.0, gain_db=-0.7, q=0.7),
            ])
        elif tonal == "sub-heavy":
            processors.extend([
                LowShelfFilter(cutoff_frequency_hz=95.0, gain_db=1.5, q=0.7),
                PeakFilter(cutoff_frequency_hz=320.0, gain_db=-0.7, q=0.9),
            ])

        if ratio > 1.0:
            rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
            rms_db = 20.0 * np.log10(max(rms, 1e-9))
            threshold = float(np.clip(rms_db + 5.0, -24.0, -8.0))
            character = profile.targets.get("compression", {}).get("character", "")
            attack = 30.0 if character in ("punchy", "gentle") else 15.0
            release = 150.0 if character in ("smooth", "gentle") else 90.0
            processors.append(Compressor(
                threshold_db=threshold,
                ratio=ratio,
                attack_ms=attack,
                release_ms=release,
            ))

        if processors:
            a = Pedalboard(processors)(a.T, sr).T.astype(np.float32)
    except Exception:
        pass

    width = float(profile.targets.get("stereo_width", 1.0))
    return _set_stereo_width(a, width)


def _set_stereo_width(audio: np.ndarray, width: float) -> np.ndarray:
    """Adjust side level in M/S space without changing the mono component."""
    if audio.ndim != 2 or audio.shape[1] < 2:
        return audio
    left, right = audio[:, 0], audio[:, 1]
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right) * np.float32(np.clip(width, 0.0, 2.0))
    out = audio.copy()
    out[:, 0] = mid + side
    out[:, 1] = mid - side
    return out.astype(np.float32)
