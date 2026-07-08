"""Heuristic mixing engine (Path A / fallback).

For each stem this module produces a MixParams object — interpretable gain,
EQ, and pan settings — derived from pairwise masking analysis and style-profile
targets. No trained model is required; this path works on every machine.

The output of mix() is a list of (audio, MixParams) pairs. The caller then
applies them via the DSP console (console.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from .analysis import StemAnalysis, ROLE_PRIORITY

# ── Data types ─────────────────────────────────────────────────────────────

@dataclass
class EQBand:
    """Single parametric EQ band: centre freq (Hz), gain (dB), Q."""
    freq: float
    gain_db: float
    q: float = 1.4


@dataclass
class MixParams:
    """Interpretable per-stem mix parameters produced by the mixer."""
    stem_path: str
    role: str
    gain_db: float          # pre-fader gain
    pan: float              # -1.0 (L) … 0.0 (C) … +1.0 (R)
    eq_bands: List[EQBand] = field(default_factory=list)
    highpass_hz: float = 0.0
    muted: bool = False

    def to_dict(self) -> dict:
        return {
            "stem_path": self.stem_path,
            "role": self.role,
            "gain_db": round(self.gain_db, 2),
            "pan": round(self.pan, 3),
            "highpass_hz": round(self.highpass_hz, 1),
            "eq_bands": [{"freq": b.freq, "gain_db": round(b.gain_db, 2), "q": b.q}
                         for b in self.eq_bands],
        }


# ── Target balance per role (dB relative to 0 dBFS bus target) ────────────
# These are starting points; the style profile shifts them.
_ROLE_TARGET_LUFS: dict[str, float] = {
    "vocal":    -16.0,
    "drums":    -18.0,
    "bass":     -19.0,
    "harmonic": -21.0,
    "other":    -22.0,
}

# Profile overrides: vocal_boost shifts everything relative to vocal
_PROFILE_VOCAL_BOOSTS: dict[str, float] = {
    "vocal-forward-rnb": +2.0,
    "warm-soul":         +1.5,
    "pop-maximal":       +1.0,
    "rhythmic-sparse":   -1.0,
    "neutral":            0.0,
}

# Pan spread by role (multiple same-role stems get spread across this window)
_PAN_SPREAD: dict[str, float] = {
    "vocal":    0.0,   # always centre
    "drums":    0.3,
    "bass":     0.1,   # nearly centre
    "harmonic": 0.7,
    "other":    0.5,
}

# Frequency ranges that commonly mask between role pairs (Hz)
_MASKING_PAIRS: list[tuple[str, str, float, float, float]] = [
    # (role_A, role_B, lo_hz, hi_hz, dip_db_on_B)
    ("vocal",    "harmonic",  1000, 3500, -2.5),
    ("vocal",    "other",     1000, 4000, -3.0),
    ("bass",     "drums",       80,  250, -2.0),
    ("drums",    "harmonic",   200,  600, -1.5),
    ("bass",     "harmonic",    80,  300, -2.0),
]


# ── Public API ────────────────────────────────────────────────────────────

def mix(analyses: list[StemAnalysis], profile_id: str = "neutral") -> list[MixParams]:
    """Return per-stem MixParams for the given stems and style profile."""
    params = [_initial_params(a) for a in analyses]
    _apply_gain_targets(params, analyses, profile_id)
    _apply_highpass(params)
    _apply_masking_eq(params, analyses)
    _apply_pan(params, analyses)
    return params


# ── Internal steps ────────────────────────────────────────────────────────

def _initial_params(a: StemAnalysis) -> MixParams:
    return MixParams(stem_path=a.path, role=a.role, gain_db=0.0, pan=0.0)


def _apply_gain_targets(params: list[MixParams],
                        analyses: list[StemAnalysis],
                        profile_id: str) -> None:
    """Solve per-stem gain to hit role-based LUFS targets."""
    vocal_boost = _PROFILE_VOCAL_BOOSTS.get(profile_id, 0.0)
    role_counts = {
        role: sum(a.role == role for a in analyses)
        for role in _ROLE_TARGET_LUFS
    }
    for p, a in zip(params, analyses):
        target = _ROLE_TARGET_LUFS.get(a.role, -20.0)
        if a.role == "vocal":
            target += vocal_boost
        # Multiple stems in one role share the role's power budget instead of
        # each being driven independently to the full target.
        count = max(role_counts.get(a.role, 1), 1)
        target -= 10.0 * np.log10(count)
        current = a.integrated_lufs
        if current > -70:
            p.gain_db = round(target - current, 2)
        else:
            p.gain_db = 0.0
        # Clamp to ±18 dB to avoid absurd boosts on silent stems
        p.gain_db = float(np.clip(p.gain_db, -18.0, 18.0))


def _apply_highpass(params: list[MixParams]) -> None:
    """Apply role-appropriate highpass to remove sub-rumble."""
    hp: dict[str, float] = {
        "vocal": 80.0, "drums": 30.0, "bass": 25.0,
        "harmonic": 60.0, "other": 60.0,
    }
    for p in params:
        p.highpass_hz = hp.get(p.role, 60.0)


def _apply_masking_eq(params: list[MixParams],
                      analyses: list[StemAnalysis]) -> None:
    """Apply complementary EQ dips where stems mask each other.

    For each masking pair: if both roles are present, dip the lower-priority
    stem in the contested band. The high-priority stem is left clear.
    """
    role_map: dict[str, list[int]] = {}
    for i, a in enumerate(analyses):
        role_map.setdefault(a.role, []).append(i)

    for role_a, role_b, lo, hi, dip in _MASKING_PAIRS:
        if role_a not in role_map or role_b not in role_map:
            continue
        # role_b gets the dip (it's lower priority per MASKING_PAIRS order)
        centre = (lo + hi) / 2.0
        q = centre / max(hi - lo, 1.0)
        for idx in role_map[role_b]:
            a_analysis = analyses[idx]
            # Only dip if the stem actually has energy in this band
            band_idx = _freq_to_band_idx(centre)
            if band_idx >= len(a_analysis.band_energy):
                continue
            loser_energy = a_analysis.band_energy[band_idx]
            winner_energy = max(
                analyses[i].band_energy[band_idx]
                for i in role_map[role_a]
                if band_idx < len(analyses[i].band_energy)
            )
            overlap = min(loser_energy, winner_energy)
            if overlap > 0.025:
                strength = float(np.clip(overlap / 0.12, 0.25, 1.0))
                params[idx].eq_bands.append(
                    EQBand(freq=centre, gain_db=dip * strength, q=q)
                )


def _apply_pan(params: list[MixParams], analyses: list[StemAnalysis]) -> None:
    """Spread same-role stems across the stereo field."""
    role_indices: dict[str, list[int]] = {}
    for i, a in enumerate(analyses):
        role_indices.setdefault(a.role, []).append(i)

    for role, indices in role_indices.items():
        spread = _PAN_SPREAD.get(role, 0.5)
        n = len(indices)
        if n == 1 or spread == 0.0:
            for i in indices:
                params[i].pan = 0.0
        else:
            positions = np.linspace(-spread, spread, n)
            for i, pos in zip(indices, positions):
                params[i].pan = round(float(pos), 3)


def _freq_to_band_idx(freq: float) -> int:
    """Map a frequency to the nearest BAND_EDGES_HZ band index."""
    edges = [20, 100, 250, 500, 1000, 2500, 5000, 10000, 20000]
    for i, hi in enumerate(edges[1:]):
        if freq < hi:
            return i
    return len(edges) - 2
