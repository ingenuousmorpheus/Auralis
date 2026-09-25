"""Vocal production (AU-09): convert every vocal part efficiently and build the backing bus.

Each part (lead, doubles, harmonies, ad-libs) is a guide vocal the size of the
song. Converting them one by one would reload Seed-VC for every part, so the
sung spans of all parts are **packed** back to back (with short silences) into
as few conversion calls as possible, converted, and **unpacked** to their
original positions. Seed-VC keeps the input length, so positions line up.

The backing parts are then shaped like a producer's stack: high-passed, sent
to a short room, panned (doubles wide left/right, harmonies half left/right,
ad-libs off-centre) and summed into one stereo ``backing_vocals`` bus that
sits under the lead. Every part is also kept as its own stem.
"""
from __future__ import annotations

import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, oaconvolve, sosfilt

SR = 44100
GAP = 1.5                         # seconds of silence between packed pieces
PAN = {"double_l": -0.75, "double_r": 0.75, "harmony_high": 0.35, "harmony_low": -0.35, "adlibs": 0.2}
LEVEL_DB = {"double_l": -5.0, "double_r": -5.0, "harmony_high": -7.0, "harmony_low": -8.0, "adlibs": -6.0}


def pack(pieces: list[tuple[str, np.ndarray, int]], max_seconds: float) -> list[dict]:
    """Group (part, audio, position) pieces into calls of at most ``max_seconds``."""
    calls, cur, length = [], [], 0
    gap = int(GAP * SR)
    for part, audio, pos in pieces:
        n = len(audio)
        if cur and (length + gap + n) / SR > max_seconds:
            calls.append(cur)
            cur, length = [], 0
        cur.append((part, audio, pos))
        length += (gap if length else 0) + n
    if cur:
        calls.append(cur)
    out = []
    for call in calls:
        buf, placements, at = [], [], 0
        for part, audio, pos in call:
            if placements:
                buf.append(np.zeros(gap, np.float32))
                at += gap
            placements.append((part, pos, at, len(audio)))
            buf.append(audio.astype(np.float32))
            at += len(audio)
        out.append({"audio": np.concatenate(buf), "placements": placements})
    return out


def convert_parts(guides: dict[str, np.ndarray], spans: dict[str, list[tuple[float, float]]], convert,
                  out_dir: str, quality: str, max_seconds: float, progress=None) -> tuple[dict, int]:
    """Convert every part's sung spans with as few ``convert`` calls as possible."""
    pieces = []
    for part, audio in guides.items():
        for a, b in spans.get(part, []):
            s0, s1 = max(0, int(a * SR)), min(len(audio), int(b * SR))
            if s1 > s0:
                pieces.append((part, audio[s0:s1], s0))
    calls = pack(pieces, max_seconds)
    converted = {part: np.zeros(len(audio), np.float32) for part, audio in guides.items()}
    for i, call in enumerate(calls):
        if progress:
            progress(i, len(calls), len(call["audio"]) / SR)
        src = os.path.join(out_dir, f"call_{i:02d}_guide.wav")
        dst = os.path.join(out_dir, f"call_{i:02d}_voice.wav")
        sf.write(src, call["audio"], SR, subtype="PCM_16")
        convert(src, dst, quality)
        y, sr = sf.read(dst, always_2d=True, dtype="float32")
        y = y.mean(axis=1)
        if sr != SR:
            from scipy.signal import resample_poly
            y = resample_poly(y, SR, sr).astype(np.float32)
        for part, pos, at, n in call["placements"]:
            seg = y[at:at + n]
            m = min(len(seg), len(converted[part]) - pos)
            converted[part][pos:pos + m] = seg[:m]
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass
    return converted, len(calls)


def _room(seed=11, seconds=0.9):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)).astype(np.float32) * np.exp(-t * 6.9 / seconds)[:, None]
    ir[: int(0.008 * SR)] = 0
    return ir / np.sqrt((ir ** 2).sum(axis=0))


def backing_bus(converted: dict[str, np.ndarray], out_dir: str, levels: dict | None = None) -> dict:
    """Shape and pan the backing parts; write each stem and the summed bus.
    ``levels`` ({part: dB}) adjusts parts relative to their producer defaults (LEVEL_DB)."""
    levels = levels or {}
    os.makedirs(out_dir, exist_ok=True)
    hp = butter(2, 180, "high", fs=SR, output="sos")
    ir = _room()
    stems, bus = {}, None
    for part, mono in converted.items():
        if part == "lead" or not np.any(np.abs(mono) > 1e-4):
            continue
        x = sosfilt(hp, mono).astype(np.float32) * 10 ** ((LEVEL_DB.get(part, -7) + float(levels.get(part, 0.0))) / 20)
        pan = PAN.get(part, 0.0)
        left, right = np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)          # constant-power pan
        st = np.stack([x * left, x * right], 1)
        wet = np.stack([oaconvolve(st[:, c], ir[:, c], mode="full")[: len(st)] for c in (0, 1)], 1)
        st = (st + 0.22 * wet).astype(np.float32)
        path = os.path.join(out_dir, f"{part}.wav")
        sf.write(path, st, SR, subtype="PCM_24")
        stems[part] = path
        bus = st.copy() if bus is None else bus + st          # every part is the song's length
    bus_path = None
    if bus is not None:
        peak = float(np.abs(bus).max()) or 1.0
        if peak > 0.89:
            bus *= 0.89 / peak
        bus_path = os.path.join(out_dir, "backing_vocals.wav")
        sf.write(bus_path, bus, SR, subtype="PCM_24")
    return {"stems": stems, "bus_path": bus_path}
