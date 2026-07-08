"""Loudness measurement and normalization (ITU-R BS.1770 via pyloudnorm).

All functions operate on float32/float64 numpy arrays shaped (samples, channels)
or (samples,) for mono. Sample rate is passed explicitly; nothing is read from
global state.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import resample_poly

try:
    import pyloudnorm as pyln
except ImportError:  # pragma: no cover - dependency missing in some envs
    pyln = None


# Common streaming / delivery targets (integrated LUFS).
LOUDNESS_TARGETS = {
    "loud": -9.0,
    "streaming": -14.0,
    "dynamic": -16.0,
}

DEFAULT_TRUE_PEAK_CEILING_DB = -1.0


@dataclass
class LoudnessStats:
    integrated_lufs: float
    true_peak_db: float


def _as_2d(audio: np.ndarray) -> np.ndarray:
    """Return audio shaped (samples, channels)."""
    if audio.ndim == 1:
        return audio[:, np.newaxis]
    return audio


def measure(audio: np.ndarray, sr: int) -> LoudnessStats:
    """Measure integrated loudness (LUFS) and true-peak (dBTP, approximated)."""
    if pyln is None:
        raise RuntimeError("pyloudnorm is required for loudness measurement")
    a = _as_2d(audio).astype(np.float64)
    meter = pyln.Meter(sr)
    integrated = float(meter.integrated_loudness(a))
    # Approximate true peak via 4x oversampling of the absolute peak.
    peak = _true_peak_db(a, sr)
    return LoudnessStats(integrated_lufs=integrated, true_peak_db=peak)


def _true_peak_db(audio: np.ndarray, sr: int, oversample: int = 4) -> float:
    """Estimate inter-sample peak using oversampled polyphase reconstruction.

    Audio is processed in overlapping blocks so a full-length song does not
    require a second, 4x-sized copy in memory.
    """
    a = _as_2d(audio)
    n = a.shape[0]
    if n < 2:
        peak = float(np.max(np.abs(a))) if a.size else 0.0
    else:
        peak = 0.0
        block = 131072
        overlap = 128
        for start in range(0, n, block):
            stop = min(start + block, n)
            lo = max(0, start - overlap)
            hi = min(n, stop + overlap)
            left_trim = (start - lo) * oversample
            right_trim = (hi - stop) * oversample
            for ch in range(a.shape[1]):
                up = resample_poly(a[lo:hi, ch], oversample, 1)
                segment = up[left_trim:len(up) - right_trim if right_trim else None]
                if segment.size:
                    peak = max(peak, float(np.max(np.abs(segment))))
    if peak <= 0:
        return -np.inf
    return 20.0 * np.log10(peak)


def normalize(audio: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    """Normalize integrated loudness to ``target_lufs`` (gain only, no limiting)."""
    if pyln is None:
        raise RuntimeError("pyloudnorm is required for loudness normalization")
    a = _as_2d(audio).astype(np.float64)
    meter = pyln.Meter(sr)
    current = meter.integrated_loudness(a)
    out = pyln.normalize.loudness(a, current, target_lufs)
    return out.astype(np.float32)


def apply_true_peak_ceiling(
    audio: np.ndarray, sr: int, ceiling_db: float = DEFAULT_TRUE_PEAK_CEILING_DB
) -> np.ndarray:
    """Scale audio down so its true peak does not exceed ``ceiling_db``.

    This is a safety gain stage, not a limiter. The mastering chain applies a
    real limiter; this guarantees the final ceiling is respected after
    normalization.
    """
    a = _as_2d(audio).astype(np.float32)
    peak = _true_peak_db(a, sr)
    if not np.isfinite(peak):
        return a
    if peak <= ceiling_db:
        return a
    gain = 10.0 ** ((ceiling_db - peak) / 20.0)
    return (a * gain).astype(np.float32)


def normalize_with_limiter(
    audio: np.ndarray,
    sr: int,
    target_lufs: float,
    ceiling_db: float = DEFAULT_TRUE_PEAK_CEILING_DB,
    max_iterations: int = 4,
) -> np.ndarray:
    """Hit a loudness target while constraining peaks with an offline limiter."""
    source = _as_2d(audio).astype(np.float32)
    source_lufs = measure(source, sr).integrated_lufs
    if not np.isfinite(source_lufs):
        return source
    gain_db = target_lufs - source_lufs
    rendered = source

    for _ in range(max_iterations):
        rendered = source * np.float32(10.0 ** (gain_db / 20.0))
        rendered = _limit(rendered, sr, ceiling_db)
        rendered = apply_true_peak_ceiling(rendered, sr, ceiling_db)
        current = measure(rendered, sr).integrated_lufs
        error = target_lufs - current
        if abs(error) <= 0.1:
            break
        gain_db += float(np.clip(error, -3.0, 3.0))

    return apply_true_peak_ceiling(rendered, sr, ceiling_db)


def _limit(audio: np.ndarray, sr: int, ceiling_db: float) -> np.ndarray:
    """Peak-limit while preserving stereo linking when Pedalboard is present."""
    try:
        from pedalboard import Limiter, Pedalboard

        board = Pedalboard([
            Limiter(threshold_db=float(ceiling_db - 0.15), release_ms=100.0)
        ])
        return board(audio.T.astype(np.float32), sr).T.astype(np.float32)
    except Exception:
        ceiling = 10.0 ** (ceiling_db / 20.0)
        drive = np.maximum(np.abs(audio) / max(ceiling, 1e-9), 1.0)
        return (audio / drive).astype(np.float32)
