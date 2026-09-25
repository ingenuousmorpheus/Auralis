"""Vocal production parts (AU-09): doubles, harmonies and ad-libs from the lead line.

Given the lead guide score (``voice.guide``) and the blueprint, write the
backing parts a producer would stack, as guide scores the same singer and the
same voice model can perform:

* **double_l / double_r**  the lead again, two separate performances panned apart
* **harmony_high**        for each lead note, the nearest chord tone a third to a
                          sixth above (a diatonic third when no chord tone fits)
* **harmony_low**         the nearest chord tone a third to a sixth below
* **adlibs**              short descending runs in the rests after phrases in the
                          last chorus and outro ("run on the phrase ending")

How much each section gets follows its **backing_vocals** level in the
blueprint arrangement (light: doubles; medium: + high harmony; full: + low
harmony and ad-libs), capped by the chosen production (lead / doubles /
harmony / full, roadmap §10). Every harmony note stays inside the singer's
range and inside the key. Nothing here reads any existing song's vocal.
"""
from __future__ import annotations

from dataclasses import replace

from .chords import ChordError, chord_tones, parse_key

PRODUCTION_TIER = {"lead": 0, "doubles": 1, "harmony": 2, "full": 3}
LEVEL_TIER = {"off": 0, "light": 1, "medium": 2, "full": 3}
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10]}
PARTS = ("double_l", "double_r", "harmony_high", "harmony_low", "adlibs")


def _section_at(bp, seconds):
    beat = seconds * float(bp["tempo"]) / 60.0
    for s in bp["sections"]:
        if (s["start_bar"] - 1) * 4 <= beat < (s["start_bar"] - 1 + s["bars"]) * 4:
            return s, beat
    return None, beat


def _chord_at(section, beat):
    start = (section["start_bar"] - 1) * 4
    best = None
    for c in section.get("chords") or []:
        if start + (c["bar"] - 1) * 4 + (c["beat"] - 1) <= beat + 1e-6:
            best = c
    return best


def _step(pitch, scale_pcs, steps):
    """Move ``steps`` scale degrees from ``pitch`` (which may be off-scale)."""
    p = pitch
    moved = 0
    direction = 1 if steps > 0 else -1
    while moved < abs(steps):
        p += direction
        if p % 12 in scale_pcs:
            moved += 1
    return p


def plan_parts(blueprint: dict, lead: list, production: str = "full") -> dict:
    """Lead guide score → {part: [GuideNote]} plus reasons."""
    tonic, mode = parse_key(blueprint["key"])
    scale = {(tonic + i) % 12 for i in SCALES[mode]}
    vr = blueprint.get("vocal") or {}
    low = int(round(vr.get("range_low_midi", 48)))
    high = int(round(vr.get("range_high_midi", 72))) - 1
    cap = PRODUCTION_TIER.get(production, 3)
    parts = {p: [] for p in PARTS}
    why = []
    last_chorus = max((i for i, s in enumerate(blueprint["sections"]) if s["type"] == "chorus"), default=None)

    tiers_seen = {}
    for i, note in enumerate(lead):
        s, beat = _section_at(blueprint, note.start)
        if s is None:
            continue
        level = (s.get("arrangement") or {}).get("backing_vocals", "off")
        tier = min(cap, LEVEL_TIER.get(level, 0))
        tiers_seen[s.get("label", s["type"])] = tier
        if tier >= 1:
            parts["double_l"].append(replace(note, start=round(note.start + 0.012, 4)))
            parts["double_r"].append(replace(note, start=round(max(0.0, note.start - 0.008), 4)))
        if tier >= 2:
            c = _chord_at(s, beat)
            pcs = set()
            if c:
                try:
                    root, tones, _ = chord_tones(c["roman"], tonic, mode)
                    pcs = {(root + t) % 12 for t in tones}
                except ChordError:
                    pcs = set()
            up = [p for p in range(note.midi + 3, note.midi + 10) if p % 12 in pcs and p % 12 in scale]
            hp = up[0] if up else _step(note.midi, scale, 2)
            if low <= hp <= high:
                parts["harmony_high"].append(replace(note, midi=hp, velocity=max(1, note.velocity - 8)))
            if tier >= 3:
                down = [p for p in range(note.midi - 9, note.midi - 2) if p % 12 in pcs and p % 12 in scale]
                lp = down[-1] if down else _step(note.midi, scale, -2)
                if low <= lp <= high:
                    parts["harmony_low"].append(replace(note, midi=lp, velocity=max(1, note.velocity - 10)))
        # ad-libs: a falling run into the rest after a phrase, in the last chorus and the outro
        is_last = s["type"] == "outro" or (last_chorus is not None and blueprint["sections"].index(s) == last_chorus)
        if tier >= 3 and is_last and note.phrase_end:
            nxt = lead[i + 1].start if i + 1 < len(lead) else note.start + note.duration + 2.0
            gap_start = note.start + note.duration + 0.05
            spb = 60.0 / float(blueprint["tempo"])
            if nxt - gap_start >= spb * 1.5:
                top = min(high, _step(note.midi, scale, 4))
                run = [top]
                for _ in range(4):
                    run.append(_step(run[-1], scale, -1))
                step = min(spb / 2, (nxt - gap_start - 0.1) / (len(run) + 1))
                for k, p in enumerate(run):
                    if low <= p <= high:
                        parts["adlibs"].append(replace(
                            note, start=round(gap_start + k * step, 4),
                            duration=round(step * (2.5 if k == len(run) - 1 else 0.95), 4), midi=p,
                            velocity=max(1, note.velocity - 6), syllable="", vowel="o", onset="",
                            phrase_end=k == len(run) - 1))

    named = {1: "doubles", 2: "doubles + high harmony", 3: "doubles + both harmonies (+ ad-libs at the end)"}
    groups = {}
    for label, tier in tiers_seen.items():
        if tier:
            groups.setdefault(named[tier], []).append(label)
    for what, labels in groups.items():
        why.append(f"{', '.join(labels)}: {what} (from the section's backing-vocals level"
                   f"{'' if cap == 3 else f', capped by “{production}”'}).")
    if not any(parts.values()):
        why.append("Lead only: no section has backing vocals switched on" if cap else "Lead only, as chosen.")
    why.append("Harmonies take the nearest chord tone a third to a sixth away and stay inside your range and the key.")
    return {"parts": parts, "why": why, "counts": {k: len(v) for k, v in parts.items()}}
