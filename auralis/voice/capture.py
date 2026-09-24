"""Microphone takes → a saved voice (the Kits / Suno "record your voice" flow).

A singer records one continuous take in the browser. This module checks the
take the way an engineer would before using it:

* level:      too quiet, healthy, or clipping
* noise:      the room floor (quietest 10% of frames) against the singing
* singing:    how many seconds actually contain voice
* reference:  the steadiest 6–20 s window of continuous singing, which becomes
              the voice's reference prompt (Seed-VC needs 3–30 s)

It returns plain-language issues and tips, and never judges the voice itself.
The whole take is then added to the voice's dataset, where the existing
``VoiceProfileStore.add_recordings`` segmentation and range/readiness analysis
run unchanged. Nothing leaves the machine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

FRAME = 0.05                   # seconds per analysis frame
MIN_SINGING = 5.0              # seconds of voice needed for an instant voice
GOOD_SINGING = 20.0
REF_MIN, REF_MAX = 6.0, 20.0


@dataclass
class TakeReport:
    duration_seconds: float
    singing_seconds: float
    peak_dbfs: float
    singing_level_dbfs: float
    noise_floor_dbfs: float
    snr_db: float
    clipping_percent: float
    reference_start: float
    reference_end: float
    usable: bool
    quality: str                                  # "great" | "good" | "usable" | "retake"
    issues: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _db(x: float) -> float:
    return float(20 * np.log10(max(x, 1e-9)))


def analyse_take(audio: np.ndarray, sr: int) -> TakeReport:
    """Check a take and choose its reference window. ``audio`` is (n,) or (n, ch)."""
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = mono.astype(np.float32)
    duration = len(mono) / sr
    hop = max(1, int(FRAME * sr))
    n = len(mono) // hop
    if n < 4:
        return TakeReport(round(duration, 2), 0.0, -120.0, -120.0, -120.0, 0.0, 0.0, 0.0, 0.0, False, "retake",
                          ["The take is too short."], ["Record at least 15 seconds of singing."])
    frames = mono[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    peak = float(np.abs(mono).max())
    clipping = float(np.mean(np.abs(mono) >= 0.999) * 100)
    floor = float(np.percentile(rms, 10))
    loud = float(np.percentile(rms, 95))
    # voice frames: well above the room floor and not far below the loud frames
    thresh = max(floor * 3.2, loud * 0.08, 10 ** (-50 / 20))
    voiced = rms >= thresh
    singing = float(voiced.sum() * FRAME)
    level = _db(float(np.median(rms[voiced]))) if voiced.any() else -120.0
    snr = level - _db(floor)

    # reference: the window (6–20 s) with the most voice and the steadiest level
    best, best_score = (0, 0), -1.0
    win_max = int(REF_MAX / FRAME)
    win_min = int(REF_MIN / FRAME)
    if n >= win_min:
        cs = np.concatenate([[0], np.cumsum(voiced)])
        for length in (win_max, int(12 / FRAME), win_min):
            length = min(length, n)
            for start in range(0, n - length + 1, max(1, int(0.5 / FRAME))):
                voice_seconds = (cs[start + length] - cs[start]) * FRAME
                seg = rms[start:start + length]
                sung = seg[seg >= thresh]
                wobble = float(np.std(_safe_db(sung))) if sung.size else 30.0   # dB spread of the singing
                clipped = float(np.mean(np.abs(mono[start * hop:(start + length) * hop]) >= 0.999))
                score = voice_seconds - 0.05 * wobble - 100 * clipped
                if score > best_score:
                    best, best_score = (start, start + length), score
    else:
        best = (0, n)
    ref_start, ref_end = best[0] * FRAME, best[1] * FRAME

    issues, tips = [], []
    if clipping > 0.1:
        issues.append(f"The take clips ({clipping:.2f}% of samples at full scale).")
        tips.append("Turn the microphone gain down or step back a little, then record again.")
    if level < -38:
        issues.append(f"The singing is quiet ({level:.0f} dBFS).")
        tips.append("Move closer to the mic (a hand's width) or raise the input gain.")
    if snr < 20:
        issues.append(f"The room is noisy: the singing is only {snr:.0f} dB above the background.")
        tips.append("Turn off fans or music, close the door, and sing closer to the mic.")
    if singing < MIN_SINGING:
        issues.append(f"Only {singing:.0f} s of singing was heard.")
        tips.append("Sing for at least 20 seconds without long pauses.")
    elif singing < GOOD_SINGING:
        tips.append("More singing gives a better voice: aim for a minute or more, low, middle and high notes.")
    usable = clipping <= 0.1 and singing >= MIN_SINGING and snr >= 12 and level >= -50
    if not usable:
        quality = "retake"
    elif snr >= 35 and singing >= 45 and level >= -30:
        quality = "great"
    elif snr >= 25 and singing >= GOOD_SINGING:
        quality = "good"
    else:
        quality = "usable"
    return TakeReport(
        duration_seconds=round(duration, 2), singing_seconds=round(singing, 1), peak_dbfs=round(_db(peak), 1),
        singing_level_dbfs=round(level, 1), noise_floor_dbfs=round(_db(floor), 1), snr_db=round(snr, 1),
        clipping_percent=round(clipping, 3), reference_start=round(ref_start, 2), reference_end=round(ref_end, 2),
        usable=usable, quality=quality, issues=issues, tips=tips,
    )


def _safe_db(x):
    return 20 * np.log10(np.maximum(np.asarray(x, np.float64), 1e-9))
