"""Stem analysis — extract perceptual features used by both the heuristic
mixer and the DSP console controller.

All functions are stateless and operate on float32 numpy arrays shaped
(samples, channels). Sample rate is passed explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import librosa
except ImportError:
    librosa = None

try:
    import pyloudnorm as pyln
except ImportError:
    pyln = None

# ── Role taxonomy ──────────────────────────────────────────────────────────
ROLES = ("vocal", "drums", "bass", "harmonic", "other")

# Priority order used when resolving masking conflicts.
# Lower index = higher priority (vocal wins over everything).
ROLE_PRIORITY: dict[str, int] = {r: i for i, r in enumerate(ROLES)}


@dataclass
class StemAnalysis:
    """Perceptual feature snapshot of one stem."""
    path: str
    role: str                        # auto-detected or user-supplied
    role_confidence: float           # 0–1; 0 when manually set

    # Loudness
    integrated_lufs: float
    crest_factor_db: float

    # Spectral
    spectral_centroid_hz: float      # brightness proxy
    spectral_bandwidth_hz: float
    spectral_flatness: float         # 0=tonal, 1=noisy
    low_energy_ratio: float          # energy below 250 Hz / total
    high_energy_ratio: float         # energy above 5 kHz / total

    # Temporal
    onset_rate_hz: float             # onsets per second → rhythmic density
    rms_db: float

    # Per-band energy (8 bark-inspired bands), normalised 0–1
    band_energy: list[float] = field(default_factory=list)

    # Stereo
    stereo_correlation: float = 1.0  # 1=mono, -1=wide


# Bark-inspired band edges (Hz) covering 20 Hz – 20 kHz in 8 bands
BAND_EDGES_HZ = [20, 100, 250, 500, 1000, 2500, 5000, 10000, 20000]


def analyse(audio: np.ndarray, sr: int, path: str = "",
            role: Optional[str] = None) -> StemAnalysis:
    """Return a StemAnalysis for ``audio``.

    If ``role`` is supplied it is used as-is (user override, confidence=0).
    Otherwise role is auto-detected from spectral heuristics.
    """
    if librosa is None:
        raise RuntimeError("librosa is required for stem analysis")

    a = _as_2d(audio)
    mono = a.mean(axis=1).astype(np.float32)

    # ── Loudness ──────────────────────────────────────────────────────────
    rms = float(np.sqrt(np.mean(mono ** 2)))
    rms_db = 20 * np.log10(max(rms, 1e-9))
    peak = float(np.max(np.abs(mono)))
    crest_db = 20 * np.log10(max(peak, 1e-9)) - rms_db

    lufs = -70.0
    if pyln is not None:
        try:
            meter = pyln.Meter(sr)
            lufs = float(meter.integrated_loudness(a.astype(np.float64)))
        except Exception:
            pass

    # ── Spectral features ─────────────────────────────────────────────────
    S = np.abs(librosa.stft(mono, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

    centroid = float(np.mean(librosa.feature.spectral_centroid(S=S, sr=sr)))
    bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(S=S, sr=sr)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=S)))

    # Band energies
    band_energy = _band_energies(S, freqs)
    low_e = sum(band_energy[:2])    # <250 Hz
    high_e = sum(band_energy[5:])   # >5 kHz

    # ── Temporal ──────────────────────────────────────────────────────────
    onset_frames = librosa.onset.onset_detect(y=mono, sr=sr)
    duration_s = len(mono) / sr
    onset_rate = len(onset_frames) / max(duration_s, 0.1)

    # ── Stereo correlation ────────────────────────────────────────────────
    if a.shape[1] >= 2:
        l, r = a[:, 0], a[:, 1]
        if np.std(l) < 1e-9 or np.std(r) < 1e-9:
            corr = 1.0
        else:
            corr = float(np.corrcoef(l, r)[0, 1])
            corr = float(np.clip(corr, -1.0, 1.0))
    else:
        corr = 1.0

    # ── Role detection ────────────────────────────────────────────────────
    filename_role = _role_from_filename(path) if role is None else None
    if role is not None:
        det_role = role
        confidence = 0.0
    elif filename_role is not None:
        det_role = filename_role
        confidence = 0.98
    else:
        det_role, confidence = _detect_role(
            centroid, bandwidth, flatness, low_e, high_e, crest_db, onset_rate
        )

    return StemAnalysis(
        path=path,
        role=det_role,
        role_confidence=confidence,
        integrated_lufs=round(lufs, 1),
        crest_factor_db=round(crest_db, 1),
        spectral_centroid_hz=round(centroid, 1),
        spectral_bandwidth_hz=round(bandwidth, 1),
        spectral_flatness=round(flatness, 4),
        low_energy_ratio=round(low_e, 4),
        high_energy_ratio=round(high_e, 4),
        onset_rate_hz=round(onset_rate, 2),
        rms_db=round(rms_db, 1),
        band_energy=[round(v, 4) for v in band_energy],
        stereo_correlation=round(corr, 3),
    )


# ── Helpers ───────────────────────────────────────────────────────────────

def _as_2d(audio: np.ndarray) -> np.ndarray:
    return audio[:, np.newaxis] if audio.ndim == 1 else audio


def _band_energies(S: np.ndarray, freqs: np.ndarray) -> list[float]:
    """Return normalised per-band energy across BAND_EDGES_HZ."""
    total = float(np.sum(S ** 2)) + 1e-12
    out = []
    edges = BAND_EDGES_HZ
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (freqs >= lo) & (freqs < hi)
        e = float(np.sum(S[mask] ** 2)) / total
        out.append(e)
    return out


def _detect_role(centroid: float, bandwidth: float, flatness: float,
                 low_e: float, high_e: float,
                 crest_db: float, onset_rate: float) -> tuple[str, float]:
    """Heuristic role detection from spectral/temporal features.

    Returns (role, confidence) where confidence is a rough 0–1 score.
    """
    scores: dict[str, float] = {r: 0.0 for r in ROLES}

    # Bass: heavy low energy, low centroid
    if low_e > 0.35:
        scores["bass"] += 0.6
    if centroid < 400:
        scores["bass"] += 0.4

    # Drums: noisy (high flatness), high onset rate, high crest
    if flatness > 0.15:
        scores["drums"] += 0.5
    if onset_rate > 3.0:
        scores["drums"] += 0.3
    if crest_db > 8:
        scores["drums"] += 0.2

    # Vocal: mid centroid (300–3500), tonal, moderate onsets, NOT too noisy
    if 300 < centroid < 3500 and flatness < 0.12:
        scores["vocal"] += 0.4
    if 0.5 < onset_rate < 8.0:
        scores["vocal"] += 0.2
    if high_e > 0.05:
        scores["vocal"] += 0.2
    if flatness < 0.08:
        scores["vocal"] += 0.2

    # Harmonic: tonal, LOW onset rate, mid-high centroid
    if flatness < 0.05:
        scores["harmonic"] += 0.4
    if onset_rate < 1.5:
        scores["harmonic"] += 0.4
    if 300 < centroid < 6000:
        scores["harmonic"] += 0.2

    # Pick winner
    best = max(scores, key=lambda k: scores[k])
    total_score = sum(scores.values()) + 1e-9
    confidence = round(scores[best] / total_score, 3)
    return best, confidence


def _role_from_filename(path: str) -> Optional[str]:
    """Use explicit DAW stem names before falling back to weak heuristics."""
    name = Path(path).stem.lower().replace("-", " ").replace("_", " ")
    tokens = set(name.split())
    aliases = {
        "vocal": {"vocal", "vocals", "vox", "leadvox", "bgv", "acapella"},
        "drums": {"drum", "drums", "kick", "snare", "hihat", "hat", "perc", "percussion"},
        "bass": {"bass", "sub", "808"},
        "harmonic": {"guitar", "gtr", "piano", "keys", "synth", "pad", "strings", "organ"},
    }
    for role_name, words in aliases.items():
        if tokens & words:
            return role_name
    return None
