"""Guide score (AU-07): the blueprint's melody guide + lyrics → what the guide singer sings.

The composer decides WHAT is sung (``composer.arrange`` writes the melody
guide inside each section's vocal register, one note per estimated syllable
when there are lyrics). This module lines the lyric syllables up with those
notes and gives each note a vowel, so a singing provider knows HOW to sing
it: pitch, timing, syllable, vowel, loudness and phrase ends (where breaths
go). Seed-VC later supplies WHO it sounds like.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

VOWELS = ("a", "e", "i", "o", "u", "uh")


@dataclass
class GuideNote:
    start: float            # seconds
    duration: float         # seconds
    midi: int
    velocity: int
    syllable: str           # "" when there are no lyrics
    vowel: str              # one of VOWELS
    onset: str              # leading consonant class: "", "hiss", "stop", "soft"
    phrase_end: bool

    def to_dict(self):
        return asdict(self)


def syllabify(line: str) -> list[str]:
    """Rough English syllables: split words at vowel groups. Good enough to
    give each melody note a vowel; not a pronunciation dictionary."""
    out = []
    for word in re.findall(r"[a-zA-Z']+", line.lower()):
        parts = re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy]*$)?", word)
        if len(parts) > 1 and re.fullmatch(r"[^aeiouy]*e", parts[-1]) and not word.endswith("le"):
            last = parts.pop()
            parts[-1] += last                        # silent final e: "love", not "lo-ve"
        out.extend(parts or [word])
    return out


def _initial_y_is_consonant(syllable: str) -> str:
    """'you', 'yeah': a y before a vowel is a consonant."""
    return re.sub(r"^y(?=[aeiou])", "", syllable)


def vowel_of(syllable: str) -> str:
    groups = re.findall(r"[aeiouy]+", _initial_y_is_consonant(syllable))
    if not groups:
        return "uh"
    g = groups[0]
    table = {"a": "a", "ai": "e", "ay": "e", "e": "e", "ee": "i", "ea": "i", "i": "i", "ie": "i", "y": "i",
             "o": "o", "oa": "o", "ow": "o", "oo": "u", "ou": "u", "u": "uh", "ue": "u", "ui": "u", "au": "o"}
    return table.get(g[:2], table.get(g[0], "uh"))


def onset_of(syllable: str) -> str:
    if re.match(r"y[aeiou]", syllable):
        return "soft"
    m = re.match(r"[^aeiouy]+", syllable)
    if not m:
        return ""
    c = m.group(0)
    if c[0] in "sfzh" or c.startswith(("sh", "ch", "th")):
        return "hiss"
    if c[0] in "tkpbdgcjqx":
        return "stop"
    return "soft"                                   # m n l r w v


def build_score(blueprint: dict, melody: list[tuple]) -> list[GuideNote]:
    """Melody notes (beats) + section lyrics → timed guide notes with syllables."""
    spb = 60.0 / float(blueprint["tempo"])
    notes = sorted(melody)
    out: list[GuideNote] = []
    for s in blueprint["sections"]:
        start_b, end_b = (s["start_bar"] - 1) * 4.0, (s["start_bar"] - 1 + s["bars"]) * 4.0
        sec = [n for n in notes if start_b <= n[0] < end_b]
        if not sec:
            continue
        # phrases = runs of notes separated by a rest of at least half a beat
        phrases, cur = [], [sec[0]]
        for a, b in zip(sec, sec[1:]):
            if b[0] - (a[0] + a[1]) >= 0.49:
                phrases.append(cur)
                cur = []
            cur.append(b)
        phrases.append(cur)
        lines = s.get("lyrics") or []
        default_vowel = "a" if s["type"] in ("chorus", "bridge") else "u"
        for pi, phrase in enumerate(phrases):
            sylls = syllabify(lines[pi % len(lines)]) if lines else []
            for ni, (beat, length, pitch, vel) in enumerate(phrase):
                syl = sylls[ni] if ni < len(sylls) else ""
                out.append(GuideNote(
                    start=round(beat * spb, 4), duration=round(length * spb, 4), midi=int(pitch), velocity=int(vel),
                    syllable=syl, vowel=vowel_of(syl) if syl else default_vowel,
                    onset=onset_of(syl) if syl else "", phrase_end=ni == len(phrase) - 1))
    return out


def phrases(score: list[GuideNote], min_gap: float = 0.25) -> list[tuple[float, float]]:
    """(start, end) seconds of each sung phrase; used to cut long songs into
    conversion chunks at rests instead of mid-word."""
    spans = []
    for n in score:
        s, e = n.start, n.start + n.duration
        if spans and s - spans[-1][1] < min_gap:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    return spans
