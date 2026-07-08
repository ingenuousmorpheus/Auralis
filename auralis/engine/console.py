"""DSP console — applies MixParams to audio via pedalboard processors.

This is the execution layer. It receives (audio, MixParams) pairs, applies
the chain per stem, then sums all stems to a stereo mix.

Future: when Diff-MST weights are available, a DiffMSTController subclass
replaces _build_chain() with transformer-predicted parameters. The console
execution layer stays unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import pedalboard
    from pedalboard import Pedalboard, HighpassFilter, LowShelfFilter, HighShelfFilter, PeakFilter, Compressor, Gain
    _PB = True
except ImportError:
    _PB = False

from .mixer import MixParams


@dataclass
class ConsoleResult:
    mix_path: str
    stem_paths: list[str]
    params: list[dict]       # serialisable params for provenance report


def apply_and_sum(
    stems: list[tuple[np.ndarray, int]],   # list of (audio, sr)
    params: list[MixParams],
    output_path: str,
    progress=None,
) -> ConsoleResult:
    """Apply MixParams to each stem and sum to a stereo mix.

    ``stems`` and ``params`` must be the same length and in the same order.
    All stems are resampled / zero-padded to match the longest one.
    Output is a 32-bit float stereo WAV at the sample rate of the first stem.
    """
    import soundfile as sf

    if not stems:
        raise ValueError("No stems provided")

    def report(s, p):
        if progress:
            progress(s, p)

    sr = stems[0][1]
    prepared = [
        (_resample(audio, stem_sr, sr) if stem_sr != sr else audio, sr)
        for audio, stem_sr in stems
    ]
    max_len = max(a.shape[0] for a, _ in prepared)
    bus = np.zeros((max_len, 2), dtype=np.float32)

    for idx, ((audio, stem_sr), p) in enumerate(zip(prepared, params)):
        report(f"processing {p.role}", 10 + int(idx / len(stems) * 70))
        if p.muted:
            continue

        processed = _apply_chain(audio, sr, p)

        # Zero-pad to bus length
        if processed.shape[0] < max_len:
            pad = max_len - processed.shape[0]
            processed = np.pad(processed, ((0, pad), (0, 0)))

        bus += processed

    # Preserve transients and create deterministic mastering headroom.
    report("summing", 85)
    peak = float(np.max(np.abs(bus))) if bus.size else 0.0
    headroom_peak = 10.0 ** (-3.0 / 20.0)
    if peak > headroom_peak:
        bus *= np.float32(headroom_peak / peak)

    report("writing", 95)
    sf.write(output_path, bus, sr, subtype="FLOAT")

    return ConsoleResult(
        mix_path=output_path,
        stem_paths=[p.stem_path for p in params],
        params=[p.to_dict() for p in params],
    )


def _apply_chain(audio: np.ndarray, sr: int, p: MixParams) -> np.ndarray:
    """Build and apply the effect chain for one stem, return stereo audio."""
    a = _to_2d(audio)

    if _PB:
        a = _apply_pedalboard(a, sr, p)
    else:
        a = _apply_simple(a, sr, p)

    pan = float(np.clip(p.pan, -1.0, 1.0))
    if a.shape[1] == 1:
        theta = (pan + 1.0) * np.pi / 4.0
        out = np.stack([
            a[:, 0] * np.cos(theta),
            a[:, 0] * np.sin(theta),
        ], axis=1)
    else:
        left_gain = 1.0 if pan <= 0.0 else float(np.cos(pan * np.pi / 2.0))
        right_gain = 1.0 if pan >= 0.0 else float(np.cos(-pan * np.pi / 2.0))
        out = np.stack([a[:, 0] * left_gain, a[:, 1] * right_gain], axis=1)

    return out.astype(np.float32)


def _apply_pedalboard(a: np.ndarray, sr: int, p: MixParams) -> np.ndarray:
    """Apply the effect chain using pedalboard (studio-quality JUCE DSP)."""
    board = Pedalboard()

    # Highpass
    if p.highpass_hz > 0:
        board.append(HighpassFilter(cutoff_frequency_hz=p.highpass_hz))

    # EQ bands (masking dips)
    for band in p.eq_bands:
        board.append(PeakFilter(
            cutoff_frequency_hz=float(band.freq),
            gain_db=float(band.gain_db),
            q=float(band.q),
        ))

    # Gain
    board.append(Gain(gain_db=float(p.gain_db)))

    # Gentle compression per role
    ratio, threshold = _role_comp(p.role)
    if ratio > 1.0:
        board.append(Compressor(threshold_db=threshold, ratio=ratio,
                                attack_ms=15, release_ms=120))

    # pedalboard expects (channels, samples). Preserve stereo stems.
    out = board(a.T.astype(np.float32), sr)
    return out.T


def _apply_simple(a: np.ndarray, sr: int, p: MixParams) -> np.ndarray:
    """Minimal fallback when pedalboard is unavailable: gain + soft HP."""
    gain = 10 ** (p.gain_db / 20.0)
    out = a * gain
    # Simple first-order highpass approximation
    if p.highpass_hz > 0:
        rc = 1.0 / (2 * np.pi * p.highpass_hz)
        dt = 1.0 / sr
        alpha = rc / (rc + dt)
        hp = np.zeros_like(out)
        hp[0] = out[0]
        for i in range(1, len(out)):
            hp[i] = alpha * (hp[i-1] + out[i] - out[i-1])
        out = hp
    return out.astype(np.float32)


def _role_comp(role: str) -> tuple[float, float]:
    """Return (ratio, threshold_db) for gentle per-role compression."""
    return {
        "vocal":    (2.5, -18.0),
        "drums":    (3.0, -15.0),
        "bass":     (2.0, -20.0),
        "harmonic": (1.5, -22.0),
        "other":    (1.5, -22.0),
    }.get(role, (1.5, -22.0))


def _to_2d(audio: np.ndarray) -> np.ndarray:
    return audio[:, np.newaxis] if audio.ndim == 1 else audio


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    from math import gcd
    from scipy.signal import resample_poly

    common = gcd(orig_sr, target_sr)
    up = target_sr // common
    down = orig_sr // common
    a2d = _to_2d(audio).astype(np.float32)
    return resample_poly(a2d, up, down, axis=0).astype(np.float32)
