"""Singing providers (AU-07): guide score → dry guide vocal.

Provider boundary for the guide singer, like Seed-VC for voice conversion.
The guide singer does not need to sound like anyone; its job is to perform
pitch, timing, note lengths, vibrato, dynamics and breaths accurately so the
user's voice model can take over.

``VocaliseSinger`` (built in, no install) is a formant singer: a band-limited
glottal source with portamento, delayed vibrato and jitter, shaped by vowel
formants (a e i o u uh) that change per syllable, with consonant-like onsets
(hiss, stop, soft) and breaths between phrases. It sings the lyric *vowels
and rhythm*, not intelligible words; a lyric-capable engine (e.g. DiffSinger,
isolated like Seed-VC) can be added behind the same interface later.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
# (frequency Hz, bandwidth Hz, gain) for three formants per vowel (adult voice, averaged)
FORMANTS = {
    "a":  [(800, 90, 1.0), (1200, 110, 0.6), (2600, 160, 0.25)],
    "e":  [(500, 70, 1.0), (1850, 120, 0.5), (2600, 160, 0.3)],
    "i":  [(300, 60, 1.0), (2300, 140, 0.45), (3000, 180, 0.3)],
    "o":  [(480, 70, 1.0), (850, 90, 0.55), (2600, 160, 0.2)],
    "u":  [(330, 60, 1.0), (800, 90, 0.35), (2400, 160, 0.15)],
    "uh": [(620, 80, 1.0), (1200, 110, 0.5), (2550, 160, 0.2)],
}


class SingingProvider:
    id = "base"
    name = "Base singer"
    sings_words = False

    def status(self) -> dict:
        return {"id": self.id, "name": self.name, "available": True, "sings_words": self.sings_words}

    def sing(self, score, total_seconds: float, seed: int = 0):
        raise NotImplementedError


def _bandpass(lo, hi):
    return butter(2, [max(40.0, lo), min(SR / 2 - 100, hi)], "band", fs=SR, output="sos")


class VocaliseSinger(SingingProvider):
    id = "vocalise"
    name = "Auralis vocalise guide (built in)"
    sings_words = False

    def sing(self, score, total_seconds: float, seed: int = 0) -> np.ndarray:
        """Render the score to a dry mono float32 vocal at 44.1 kHz."""
        rng = np.random.default_rng(seed + 33)
        n_total = int(total_seconds * SR) + SR
        out = np.zeros(n_total, np.float32)
        if not score:
            return out
        filters = {v: [(_bandpass(f - bw, f + bw), g) for f, bw, g in fs] for v, fs in FORMANTS.items()}

        # Pitch contour over each phrase, with 40 ms glides between notes.
        groups, cur = [], [score[0]]
        for a, b in zip(score, score[1:]):
            if a.phrase_end or b.start - (a.start + a.duration) > 0.25:
                groups.append(cur)
                cur = []
            cur.append(b)
        groups.append(cur)

        for phrase in groups:
            p0 = int(phrase[0].start * SR)
            p1 = int((phrase[-1].start + phrase[-1].duration) * SR) + int(0.08 * SR)
            n = p1 - p0
            if n <= 0:
                continue
            t = np.arange(n) / SR
            midi = np.zeros(n, np.float64)
            amp = np.zeros(n, np.float64)
            for k, note in enumerate(phrase):
                a = int(note.start * SR) - p0
                b = min(n, int((note.start + note.duration) * SR) - p0)
                if k + 1 < len(phrase):
                    b = max(b, int(phrase[k + 1].start * SR) - p0)
                midi[a:b] = note.midi
                amp[a:b] = note.velocity / 127
            # glide: smooth pitch steps over ~40 ms
            glide = int(0.04 * SR)
            kernel = np.ones(glide) / glide
            midi = np.convolve(np.pad(midi, (glide // 2, glide - glide // 2 - 1), mode="edge"), kernel, "valid")
            # vibrato on held notes, after 150 ms, plus small jitter
            vib = np.zeros(n)
            for note in phrase:
                if note.duration > 0.35:
                    a = int((note.start + 0.15) * SR) - p0
                    b = min(n, int((note.start + note.duration) * SR) - p0)
                    if b > a:
                        tt = np.arange(b - a) / SR
                        vib[a:b] = 0.28 * np.sin(2 * np.pi * 5.4 * tt) * np.clip(tt / 0.25, 0, 1)
            jitter = np.convolve(rng.standard_normal(n), np.ones(441) / 441, "same") * 0.35
            f0 = 440.0 * 2 ** ((midi + vib + jitter * 0.1 - 69) / 12)
            phase = 2 * np.pi * np.cumsum(f0) / SR
            # band-limited glottal-like source: harmonics falling ~12 dB/oct, up to 5 kHz
            n_h = int(min(40, 5000 / max(1.0, f0.min())))
            src = np.zeros(n)
            for h in range(1, n_h + 1):
                src += np.sin(h * phase) / h ** 1.6 * (f0 * h < 5500)
            src += 0.02 * rng.standard_normal(n)                        # breathiness
            # vowel formants per note, crossfaded over 30 ms
            voiced = np.zeros(n)
            fade = int(0.03 * SR)
            for k, note in enumerate(phrase):
                a = max(0, int(note.start * SR) - p0 - fade)
                b = min(n, (int(phrase[k + 1].start * SR) - p0 if k + 1 < len(phrase)
                            else int((note.start + note.duration) * SR) - p0 + int(0.06 * SR)) + fade)
                seg = src[a:b]
                shaped = sum(g * sosfilt(sos, seg) for sos, g in filters[note.vowel])
                w = np.ones(len(seg))
                ramp = min(fade, len(seg) // 2)
                if ramp:
                    w[:ramp] = np.linspace(0, 1, ramp)
                    w[-ramp:] = np.linspace(1, 0, ramp)
                voiced[a:b] += shaped * w
            # loudness: note velocities, soft attack, release at the phrase end
            env = np.convolve(amp, np.ones(882) / 882, "same")
            env *= np.clip(t / 0.03, 0, 1) * np.clip((t[-1] - t) / 0.08, 0, 1)
            y = voiced * env
            # consonant-like onsets and a breath before the phrase
            for note in phrase:
                a = int(note.start * SR) - p0
                if note.onset == "hiss":
                    m = int(0.06 * SR)
                    burst = sosfilt(_bandpass(4000, 10000), rng.standard_normal(m)) * np.hanning(m) * 0.25
                elif note.onset == "stop":
                    m = int(0.015 * SR)
                    burst = sosfilt(_bandpass(1500, 6000), rng.standard_normal(m)) * np.exp(-np.arange(m) / (0.004 * SR)) * 0.4
                else:
                    continue
                s0 = max(0, a - m // 2)
                y[s0:s0 + m] += burst[: len(y[s0:s0 + m])] * note.velocity / 127
            breath_len = int(0.25 * SR)
            b0 = max(0, p0 - breath_len)
            breath = sosfilt(_bandpass(800, 4000), rng.standard_normal(p0 - b0)) * np.hanning(p0 - b0) * 0.03
            out[b0:p0] += breath.astype(np.float32)
            out[p0:p1] += y.astype(np.float32)[: len(out[p0:p1])]

        # level for voice conversion: about -20 dBFS RMS on the sung parts, peaks below -3 dBFS
        sung = np.abs(out) > 1e-4
        rms = float(np.sqrt(np.mean(out[sung] ** 2))) if sung.any() else 1.0
        gain = min(10 ** (-20 / 20) / max(rms, 1e-9), 10 ** (-3 / 20) / max(float(np.abs(out).max()), 1e-9))
        return (out * gain).astype(np.float32)


PROVIDERS = {"vocalise": VocaliseSinger()}


def get_singer(provider_id: str = "vocalise") -> SingingProvider:
    if provider_id not in PROVIDERS:
        raise KeyError(f"Unknown singing provider: {provider_id}")
    return PROVIDERS[provider_id]
