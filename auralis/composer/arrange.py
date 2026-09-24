"""Structured composer (AU-05): Song Blueprint → note tracks.

Turns a blueprint into playable parts, deterministically for a given seed:

* **keys**    voice-led chord voicings (each chord moves as little as possible
              from the last), comping rhythm set by the section's level
* **pad**     sustained voicings an octave up, where the arrangement has a pad
* **bass**    root (or slash-bass) patterns with approach notes into the next
              chord; 808-style long notes for eras whose palette has an 808
* **drums**   General-MIDI kit patterns chosen from the Atlas groove feel,
              densities from the arrangement level, fills into choruses
* **fx**      risers into choruses, impacts on arrivals, a downlifter at the outro
* **melody**  a *guide* lead line inside each section's vocal register, one
              phrase per lyric line when there are lyrics. It is written fresh
              from rules (chord tones on strong beats, steps between, the vocal
              pattern's contour and phrase length) and is kept out of the
              instrumental; the guide singer (AU-07) will use it.

A note is ``(start_beat, length_beats, midi_pitch, velocity)``. Nothing here
reads any song's melody: the only inputs are the blueprint and the seed.
"""
from __future__ import annotations

import random
import re

from .chords import ChordError, chord_tones, parse_key

# General MIDI drum notes.
KICK, RIM, SNARE, CLAP, HAT, OPEN_HAT, CRASH, TOM_LO, TOM_HI = 36, 37, 38, 39, 42, 46, 49, 45, 50
# FX "notes" understood by the renderer.
FX_RISER, FX_IMPACT, FX_DOWN = 60, 61, 62

LEVEL_VEL = {"off": 0, "light": 62, "medium": 84, "full": 104}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
KEYS_RANGE = (52, 76)       # E3–E5, the comping register
PAD_RANGE = (60, 86)
BASS_CENTRE = 40            # E2


def _vel(level: str, energy: float, accent: float = 1.0) -> int:
    base = LEVEL_VEL.get(level, 0)
    if not base:
        return 0
    return int(max(1, min(127, base * (0.75 + 0.35 * energy) * accent)))


def _voicing(pcs: list[int], prev: list[int] | None, lo: int, hi: int, n: int = 4) -> list[int]:
    """Pick the octave placement of these pitch classes that moves least from
    ``prev`` (smooth voice leading), inside [lo, hi]."""
    pcs = pcs[:n]
    best, best_cost = None, None
    for base in range(lo - 12, hi):
        # stack each pitch class at or above `base`, one inversion per base
        notes = sorted(base + ((pc - base) % 12) for pc in pcs)
        if notes[0] < lo or notes[-1] > hi:
            continue
        if prev:
            cost = sum(abs(a - b) for a, b in zip(notes, sorted(prev))) + 3 * abs(len(notes) - len(prev))
        else:
            cost = abs((notes[0] + notes[-1]) / 2 - (lo + hi) / 2)
        if best_cost is None or cost < best_cost:
            best, best_cost = notes, cost
    return best or sorted(lo + (pc - lo) % 12 for pc in pcs)


def _chord_pcs(chord: dict, tonic: int, mode: str):
    try:
        root, tones, bass = chord_tones(chord["roman"], tonic, mode)
    except ChordError:
        return None
    return root, [(root + t) % 12 for t in tones], bass


def _keys_voicing_pcs(root, pcs):
    """Rootless when the chord is rich (the bass has the root): drop the
    root and the fifth first, keep 3rd/7th/extensions."""
    if len(pcs) >= 5:
        pcs = [p for p in pcs if p not in (root, (root + 7) % 12)] or pcs
    elif len(pcs) == 4:
        pcs = [p for p in pcs if p != root] or pcs
    return pcs


# Comping hits within a chord: (beat offset, length, accent), by level.
KEYS_RHYTHM = {
    "light": [(0.0, None, 1.0)],
    "medium": [(0.0, 1.5, 1.0), (1.5, None, 0.85)],
    "full": [(0.0, 1.0, 1.0), (1.5, 0.5, 0.8), (2.0, 1.0, 0.9), (3.5, None, 0.75)],
}

# Drum patterns: per bar, (beat, drum, accent). "{sync}" variants add off-beat kicks.
DRUMS = {
    "hiphop":      {"kick": [0, 1.75, 2.5], "snare": [1, 3], "hat": 0.5},
    "straight":    {"kick": [0, 2], "snare": [1, 3], "hat": 0.5},
    "laid_back":   {"kick": [0, 2.5], "snare": [1, 3], "hat": 0.25},
    "deep_pocket": {"kick": [0, 0.75, 2.5], "snare": [1, 3], "hat": 0.25},
    "swing":       {"kick": [0, 2.5], "snare": [1, 3], "hat": 0.25},
    "half_time":   {"kick": [0, 1.75], "snare": [2], "hat": 0.25},
}


def arrange(blueprint: dict, seed: int = 0) -> dict:
    tonic, mode = parse_key(blueprint["key"])
    rng = random.Random(f"{blueprint.get('id')}:{seed}")
    tempo = float(blueprint["tempo"])
    groove = blueprint.get("groove") or {}
    feel = groove.get("feel", "straight")
    if groove.get("id") == "half_time_modern" or tempo >= 118:
        feel = "half_time"
    sync = float(groove.get("syncopation") or 0.4)
    palette = " ".join(blueprint.get("arrangement", {}).get("palette", [])).lower()
    bass_style = "808" if "808" in palette else "synth"

    tracks = {k: [] for k in ("keys", "pad", "bass", "drums", "fx", "melody")}
    prev_keys = prev_pad = None
    sections = blueprint["sections"]
    for si, s in enumerate(sections):
        start = (s["start_bar"] - 1) * 4.0
        bars = int(s["bars"])
        arr = s.get("arrangement", {})
        energy = float(s.get("energy", 0.5))
        chords = s.get("chords") or []
        nxt = sections[si + 1] if si + 1 < len(sections) else None

        # ── keys and pad ────────────────────────────────────────────────
        for ci, c in enumerate(chords):
            got = _chord_pcs(c, tonic, mode)
            if not got:
                continue
            root, pcs, bass_pc = got
            c_start = start + (c["bar"] - 1) * 4 + (c["beat"] - 1)
            length = float(c["beats"])
            if arr.get("keys", "off") != "off":
                voicing = _voicing(_keys_voicing_pcs(root, pcs), prev_keys, *KEYS_RANGE)
                prev_keys = voicing
                # the comping pattern repeats every bar the chord lasts
                pattern = KEYS_RHYTHM[arr["keys"]]
                hits = [(bar_off + off, dur, acc) for bar_off in range(0, max(1, int(length + 0.999)), 4)
                        for off, dur, acc in pattern]
                for h, (off, dur, acc) in enumerate(hits):
                    if off >= length:
                        continue
                    nxt_hit = next((o for o, _, _ in hits[h + 1:] if o < length), length)
                    d = (nxt_hit - off) if dur is None else min(dur, length - off)
                    v = _vel(arr["keys"], energy, acc)
                    for p in voicing:
                        tracks["keys"].append((c_start + off, d * 0.95, p, max(1, v - rng.randint(0, 6))))
            if arr.get("pad", "off") != "off":
                voicing = _voicing(pcs, prev_pad, *PAD_RANGE, n=5)
                prev_pad = voicing
                v = _vel(arr["pad"], energy, 0.8)
                for p in voicing:
                    tracks["pad"].append((c_start, length, p, v))

            # ── bass ────────────────────────────────────────────────────
            if arr.get("bass", "off") != "off":
                b = BASS_CENTRE - 6 + ((bass_pc - (BASS_CENTRE - 6)) % 12)       # B♭1–A2
                next_c = chords[ci + 1] if ci + 1 < len(chords) else None
                level = arr["bass"]
                v = _vel(level, energy)
                if bass_style == "808" or level == "light":
                    tracks["bass"].append((c_start, length * 0.95, b, v))
                else:
                    pattern = [(0.0, 1.5, 0), (1.5, 0.5, 0), (2.0, 1.0, 12 if level == "full" else 0)]
                    if sync > 0.45:
                        pattern = [(0.0, 0.75, 0), (0.75, 0.75, 0), (2.5, 1.0, 7 if level == "full" else 0)]
                    for off, d, iv in pattern:
                        if off < length:
                            tracks["bass"].append((c_start + off, min(d, length - off) * 0.95, b + iv,
                                                   max(1, v - (0 if off == 0 else 10))))
                    # chromatic approach into the next chord's bass on the last half beat
                    if next_c and length >= 2 and level == "full":
                        got_n = _chord_pcs(next_c, tonic, mode)
                        if got_n:
                            target = b + (((got_n[2] - bass_pc) + 6) % 12) - 6
                            approach = target - 1 if target > b else target + 1
                            tracks["bass"].append((c_start + length - 0.5, 0.45, approach, v - 14))

        # ── drums ───────────────────────────────────────────────────────
        level = arr.get("drums", "off")
        if level != "off":
            pat = DRUMS.get(feel, DRUMS["straight"])
            for bar in range(bars):
                t0 = start + bar * 4
                last_bar = bar == bars - 1
                fill = last_bar and nxt is not None and nxt["type"] == "chorus" and level != "light"
                kicks = pat["kick"] if level != "light" else [0]
                for k in kicks:
                    if fill and k >= 2:
                        continue
                    tracks["drums"].append((t0 + k, 0.25, KICK, _vel(level, energy, 1.0 if k == 0 else 0.85)))
                for sn in pat["snare"]:
                    if fill and sn >= 2:
                        continue
                    drum = RIM if level == "light" else SNARE
                    tracks["drums"].append((t0 + sn, 0.25, drum, _vel(level, energy)))
                    if level == "full" and feel in ("hiphop", "half_time"):
                        tracks["drums"].append((t0 + sn, 0.25, CLAP, _vel(level, energy, 0.7)))
                step = pat["hat"] if level != "light" else 1.0
                if level == "full" and step > 0.25 and energy > 0.75:
                    step = 0.25
                h = 0.0
                while h < 4 - 1e-9:
                    if not (fill and h >= 2):
                        acc = 1.0 if abs(h - round(h)) < 1e-9 else 0.72
                        drum = OPEN_HAT if (level == "full" and abs(h - 3.5) < 1e-9) else HAT
                        tracks["drums"].append((t0 + h, 0.2, drum, _vel(level, energy, acc * 0.8)))
                    h += step
                if level != "light" and feel in ("laid_back", "deep_pocket", "swing") and rng.random() < 0.5:
                    tracks["drums"].append((t0 + 2.75, 0.2, SNARE, _vel(level, energy, 0.35)))   # ghost
                if fill:
                    for i, b16 in enumerate([2, 2.25, 2.5, 2.75, 3, 3.25, 3.5, 3.75]):
                        drum = SNARE if i < 4 else (TOM_HI if i < 6 else TOM_LO)
                        tracks["drums"].append((t0 + b16, 0.2, drum, _vel(level, energy, 0.6 + 0.05 * i)))
            if s["type"] == "chorus" or (si > 0 and sections[si - 1]["type"] == "pre-chorus"):
                tracks["drums"].append((start, 2.0, CRASH, _vel(level, energy, 0.9)))

        # ── fx ──────────────────────────────────────────────────────────
        if nxt is not None and nxt["type"] == "chorus" and arr.get("fx", "off") != "off":
            length = min(8.0, bars * 4.0)
            tracks["fx"].append((start + bars * 4 - length, length, FX_RISER, _vel(arr["fx"], energy)))
        if s["type"] == "chorus" and si > 0:
            tracks["fx"].append((start, 4.0, FX_IMPACT, _vel("medium", energy)))
        if s["type"] == "outro":
            tracks["fx"].append((start, 8.0, FX_DOWN, _vel("light", energy)))

    tracks["melody"] = _melody(blueprint, tonic, mode, rng)
    for k in tracks:
        tracks[k].sort()
    return {
        "tempo": tempo, "key": blueprint["key"], "meter": "4/4", "seed": seed,
        "total_beats": blueprint["total_bars"] * 4, "feel": feel, "bass_style": bass_style,
        "swing": _swing(groove), "offsets_ms": groove.get("offsets_ms") or {},
        "tracks": tracks,
        "counts": {k: len(v) for k, v in tracks.items()},
    }


def _swing(groove):
    lo, hi = (groove.get("swing_ratio") or [0.5, 0.5])[:2]
    return round((lo + hi) / 2, 3)


# ── Melody guide ────────────────────────────────────────────────────────────

def _syllables(line: str) -> int:
    words = re.findall(r"[a-zA-Z']+", line.lower())
    count = 0
    for w in words:
        groups = re.findall(r"[aeiouy]+", w)
        n = len(groups) - (1 if w.endswith("e") and len(groups) > 1 and not w.endswith("le") else 0)
        count += max(1, n)
    return count


def _melody(bp, tonic, mode, rng):
    """Guide lead line: one phrase every 1–2 bars inside the section register."""
    scale = SCALES[mode]
    notes = []
    hook_cell = None
    for s in bp["sections"]:
        v = s.get("vocal")
        if not v or s.get("arrangement", {}).get("lead_vocal", "off") == "off":
            continue
        lo, hi, peak = int(v["low_midi"]), int(v["high_midi"]), int(v["peak_midi"])
        pool = [p for p in range(lo, hi + 1) if (p - tonic) % 12 in scale]
        if len(pool) < 3:
            continue
        start = (s["start_bar"] - 1) * 4.0
        bars = int(s["bars"])
        lines = s.get("lyrics") or []
        phrase_bars = 2 if s["type"] in ("chorus", "bridge") else 1
        n_phrases = max(1, bars // phrase_bars)
        chords = s.get("chords") or []
        is_chorus = s["type"] == "chorus"
        for ph in range(n_phrases):
            p_start = start + ph * phrase_bars * 4
            if is_chorus and hook_cell and ph % 2 == 1:
                # hook repetition: the chorus answers itself with the same cell
                for (off, d, pitch, vel) in hook_cell:
                    notes.append((p_start + off, d, pitch, vel))
                continue
            n = _syllables(lines[ph]) if ph < len(lines) else rng.randint(5, 8 if is_chorus else 7)
            n = max(3, min(n, 14))
            span = phrase_bars * 4 - 1.0                          # leave a breath at the end
            pickup = 0.5 if rng.random() < 0.5 else 0.0
            step = max(0.25, min(1.0, round((span - pickup) / n * 4) / 4))
            chord_at = lambda beat: next((c for c in reversed(chords)
                                          if (c["bar"] - 1) * 4 + (c["beat"] - 1) <= beat - start), None)
            # contour target: verses fall/wave in the lower half, choruses arch up to the peak
            top = peak if is_chorus or s["type"] == "bridge" else min(peak, pool[len(pool) * 2 // 3])
            idx = min(range(len(pool)), key=lambda i: abs(pool[i] - (lo + top) // 2))
            phrase = []
            t = p_start + pickup
            for i in range(n):
                if t >= p_start + span:
                    break
                progress = i / max(1, n - 1)
                target = top if (is_chorus and 0.3 < progress < 0.7) else (lo + top) // 2
                strong = abs(t - round(t)) < 1e-9
                c = chord_at(t)
                if strong and c:
                    got = _chord_pcs(c, tonic, mode)
                    tones = [p for p in pool if got and p % 12 in got[1]]
                    if tones:
                        cand = min(tones, key=lambda p: abs(p - pool[idx]) + 0.3 * abs(p - target))
                        idx = pool.index(cand)
                else:
                    direction = 1 if pool[idx] < target else -1
                    if rng.random() < 0.25:
                        direction = -direction
                    idx = max(0, min(len(pool) - 1, idx + direction))
                d = step * (2 if i == n - 1 else 1)
                phrase.append((t - p_start, min(d, p_start + span - t), pool[idx], 90 if strong else 78))
                t += step
            if is_chorus and hook_cell is None:
                hook_cell = phrase
            for (off, d, pitch, vel) in phrase:
                notes.append((p_start + off, d, pitch, vel))
    return notes
