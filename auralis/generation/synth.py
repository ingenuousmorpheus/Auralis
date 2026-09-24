"""Local synth provider: renders arrangements with small numpy instruments.

Deterministic DSP only (no samples, no downloads, no models): an FM electric
piano, a detuned-saw pad, synth and 808 basses, a synthesized drum kit, FX
sweeps and a plain "oo" tone for the melody guide. Groove comes from the
arrangement: swing on off-beat sixteenths and per-part timing offsets from the
Atlas groove profile, plus a little seeded humanising.

Quality target: a clear, musical sketch of the blueprint that the existing
mix/master pipeline can finish, not a replacement for real instruments. Better
instruments arrive as other providers behind the same interface.
"""
from __future__ import annotations

import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, oaconvolve, sawtooth, sosfilt

from .base import RenderProvider, RenderResult

SR = 44100
PARTS = ("drums", "bass", "keys", "pad", "fx")          # instrumental stems
# Atlas offsets are named by drum/bass/comping; map parts onto them.
OFFSET_KEY = {"drums": "snare", "bass": "bass", "keys": "comping", "pad": "comping"}


def _hz(pitch: float) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def _env(n: int, attack: float, decay_rate: float, release_at: int, release: float) -> np.ndarray:
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t * decay_rate)
    if release_at < n:
        r = np.arange(n - release_at) / SR
        env[release_at:] *= np.exp(-r / max(release, 1e-3) * 4)
    return env.astype(np.float32)


def _lp(x, hz, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x, axis=0).astype(np.float32)


def _hp(x, hz, order=2):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x, axis=0).astype(np.float32)


def _bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x, axis=0).astype(np.float32)


class Instruments:
    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self._drums: dict[int, np.ndarray] = {}

    def noise(self, n):
        return self.rng.standard_normal(n).astype(np.float32)

    # ── tonal ───────────────────────────────────────────────────────────
    def ep(self, pitch, dur, vel):
        f = _hz(pitch)
        n = int((dur + 0.5) * SR)
        t = np.arange(n) / SR
        v = vel / 127
        index = (0.6 + 1.6 * v) * np.exp(-t * 5)
        tone = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * t))
        tine = 0.18 * v * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t * 30)
        env = _env(n, 0.003, 1.0 + f / 900, int(dur * SR), 0.35)
        return ((tone + tine) * env * v * 0.5).astype(np.float32)

    def pad(self, pitch, dur, vel):
        f = _hz(pitch)
        n = int((dur + 1.0) * SR)
        t = np.arange(n) / SR
        out = np.zeros((n, 2), np.float32)
        for ch, cents in ((0, (-9, 4)), (1, (-4, 9))):
            for c in cents:
                out[:, ch] += sawtooth(2 * np.pi * f * 2 ** (c / 1200) * t + ch)
        env = _env(n, 0.45, 0.05, int(dur * SR), 0.9)
        return out * env[:, None] * (vel / 127) * 0.12

    def bass(self, pitch, dur, vel, style="synth"):
        f = _hz(pitch)
        v = vel / 127
        if style == "808":
            n = int((dur + 0.3) * SR)
            t = np.arange(n) / SR
            glide = f * (1 + 0.5 * np.exp(-t * 60))
            phase = 2 * np.pi * np.cumsum(glide) / SR
            x = np.tanh(1.8 * np.sin(phase)) * _env(n, 0.002, 0.8, int(dur * SR), 0.2)
            return (x * v * 0.7).astype(np.float32)
        n = int((dur + 0.15) * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * f * t) + 0.35 * _lp(sawtooth(2 * np.pi * f * t).astype(np.float32), 700)
        return (np.tanh(1.3 * x) * _env(n, 0.004, 1.5, int(dur * SR), 0.08) * v * 0.6).astype(np.float32)

    def voice(self, pitch, dur, vel):
        f = _hz(pitch)
        n = int((dur + 0.12) * SR)
        t = np.arange(n) / SR
        vib = 1 + 0.012 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.2) * 4, 0, 1)
        phase = 2 * np.pi * np.cumsum(f * vib) / SR
        x = np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.1 * np.sin(3 * phase)
        return (x * _env(n, 0.03, 0.2, int(dur * SR), 0.1) * (vel / 127) * 0.4).astype(np.float32)

    # ── drums (rendered once per sound) ─────────────────────────────────
    def drum(self, note):
        if note in self._drums:
            return self._drums[note]
        def sweep(f0, f1, rate, length, decay):
            n = int(length * SR)
            t = np.arange(n) / SR
            f = f1 + (f0 - f1) * np.exp(-t * rate)
            return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * decay)
        if note == 36:        # kick
            x = sweep(150, 48, 28, 0.45, 9) + 0.3 * _hp(self.noise(int(0.45 * SR)), 3000) * np.exp(-np.arange(int(0.45 * SR)) / SR * 300)
        elif note in (38, 37):  # snare / rim
            n = int((0.25 if note == 38 else 0.06) * SR)
            t = np.arange(n) / SR
            body = np.sin(2 * np.pi * (190 if note == 38 else 1700) * t) * np.exp(-t * 30)
            x = (0.6 * body + (0.9 if note == 38 else 0.4) * _bp(self.noise(n), 1500, 7000) * np.exp(-t * (18 if note == 38 else 60)))
        elif note == 39:      # clap
            n = int(0.3 * SR)
            t = np.arange(n) / SR
            env = sum(np.exp(-np.clip(t - d, 0, None) * 90) * (t >= d) for d in (0, 0.011, 0.022)) + 0.3 * np.exp(-t * 12)
            x = _bp(self.noise(n), 900, 3500) * env
        elif note in (42, 46):  # hats
            n = int((0.08 if note == 42 else 0.4) * SR)
            t = np.arange(n) / SR
            x = _hp(self.noise(n), 7000) * np.exp(-t * (55 if note == 42 else 8)) * 0.6
        elif note == 49:      # crash
            n = int(1.8 * SR)
            t = np.arange(n) / SR
            x = _hp(self.noise(n), 4000) * np.exp(-t * 2.2) * 0.5
        elif note in (45, 50):  # toms
            x = sweep(180 if note == 50 else 120, 120 if note == 50 else 80, 18, 0.35, 10) * 0.8
        else:
            x = np.zeros(1)
        self._drums[note] = np.asarray(x, np.float32)
        return self._drums[note]

    # ── fx ──────────────────────────────────────────────────────────────
    def fx(self, note, dur, vel):
        n = int((dur + 1.5) * SR)
        t = np.arange(n) / SR
        v = vel / 127
        if note == 60:        # riser: noise and a sine sweeping up, swelling
            ramp = np.clip(t / max(dur, 0.1), 0, 1) ** 2 * (t <= dur)
            f = 200 * 10 ** (np.clip(t / max(dur, 0.1), 0, 1))
            x = 0.5 * _bp(self.noise(n), 800, 9000) * ramp + 0.2 * np.sin(2 * np.pi * np.cumsum(f) / SR) * ramp
        elif note == 61:      # impact: low boom plus a noise burst
            x = np.sin(2 * np.pi * (45 + 60 * np.exp(-t * 20)) * t) * np.exp(-t * 2.5) + \
                0.4 * _hp(self.noise(n), 2000) * np.exp(-t * 4)
        else:                 # downlifter
            fall = np.clip(1 - t / max(dur, 0.1), 0, 1)
            f = 150 * 10 ** fall
            x = (0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * _bp(self.noise(n), 300, 5000)) * fall
        return (x * v * 0.5).astype(np.float32)


def _reverb_ir(seconds=1.8, seed=7):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)).astype(np.float32) * np.exp(-t * 6.9 / seconds)[:, None]
    ir[: int(0.012 * SR)] = 0                      # pre-delay
    return _lp(ir, 6000) / np.sqrt((ir ** 2).sum(axis=0))


class SynthRenderer(RenderProvider):
    id = "synth"
    name = "Auralis synth (local)"
    description = "Built-in numpy instruments: FM electric piano, saw pad, synth/808 bass, synthesized drums, FX."

    def render(self, arrangement: dict, out_dir: str, seed: int = 0, progress=None) -> RenderResult:
        os.makedirs(out_dir, exist_ok=True)
        tempo = float(arrangement["tempo"])
        spb = 60.0 / tempo
        swing = float(arrangement.get("swing") or 0.5)
        offsets = arrangement.get("offsets_ms") or {}
        total = arrangement["total_beats"] * spb + 3.0
        n_total = int(total * SR)
        inst = Instruments(seed)
        jitter = np.random.default_rng(seed + 1)
        ir = _reverb_ir()

        def when(beat, part):
            whole = np.floor(beat)
            frac = beat - whole
            eighth = np.floor(frac * 2) / 2
            if abs((frac - eighth) - 0.25) < 1e-6:          # off-beat sixteenth → swing
                frac = eighth + swing * 0.5
            lo_hi = offsets.get(OFFSET_KEY.get(part, ""), [0, 0])
            ms = (lo_hi[0] + lo_hi[1]) / 2 if lo_hi else 0
            return (whole + frac) * spb + ms / 1000.0 + jitter.normal(0, 0.003)

        stems, extras = {}, {}
        parts = [p for p in PARTS if arrangement["tracks"].get(p)] + \
            (["melody"] if arrangement["tracks"].get("melody") else [])
        for i, part in enumerate(parts):
            if progress:
                progress(f"rendering {part}", 100.0 * i / max(1, len(parts)))
            buf = np.zeros((n_total, 2), np.float32)
            for start, length, pitch, vel in arrangement["tracks"][part]:
                t0 = max(0, int(when(start, part) * SR))
                dur = length * spb
                if part == "drums":
                    x = inst.drum(int(pitch)) * (vel / 127)
                elif part == "keys":
                    x = inst.ep(pitch, dur, vel)
                elif part == "pad":
                    x = inst.pad(pitch, dur, vel)
                elif part == "bass":
                    x = inst.bass(pitch, dur, vel, arrangement.get("bass_style", "synth"))
                elif part == "fx":
                    x = inst.fx(int(pitch), dur, vel)
                else:
                    x = inst.voice(pitch, dur, vel)
                if x.ndim == 1:
                    if part == "drums" and pitch in (42, 46):
                        x = np.stack([x * 0.8, x * 1.0], 1)            # hats a little right
                    elif part == "keys":
                        x = np.stack([x, np.concatenate([np.zeros(int(0.004 * SR), np.float32), x])[: len(x)]], 1)
                    else:
                        x = np.stack([x, x], 1)
                end = min(n_total, t0 + len(x))
                if end > t0:
                    buf[t0:end] += x[: end - t0]
            if part == "pad":
                buf = _lp(buf, 2200)
            wet = {"keys": 0.18, "pad": 0.3, "drums": 0.07, "fx": 0.3, "melody": 0.12}.get(part, 0.0)
            if wet:
                rev = np.stack([oaconvolve(buf[:, c], ir[:, c], mode="full")[:n_total] for c in (0, 1)], 1)
                buf = buf + wet * rev.astype(np.float32)
            if part == "bass":
                buf = _hp(buf, 30)
            peak = float(np.max(np.abs(buf))) or 1.0
            buf *= 0.89 / peak
            path = os.path.join(out_dir, f"{'melody_guide' if part == 'melody' else part}.wav")
            sf.write(path, buf, SR, subtype="PCM_24")
            (extras if part == "melody" else stems)[part] = path
            del buf
        return RenderResult(stems=stems, sample_rate=SR, duration_seconds=round(total, 2),
                            provider=self.id, extras=extras)
