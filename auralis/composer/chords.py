"""Keys and Roman numerals → chord names.

Roman numerals follow the Atlas and the library analysis: every numeral is
measured from the tonic on the major scale, and borrowed degrees carry their
accidental (``♭VI``, ``♭VII``). Case gives the triad quality (``ii`` minor,
``IV`` major), a suffix adds colour (``maj7``, ``9``, ``sus``), and a slash
names the bass (``IV/V`` is IV over the fifth degree, ``IVmaj7/1`` over the
tonic). The same numerals therefore work in any key, which is what makes a
blueprint transposable.
"""
from __future__ import annotations

import re

from ..theory.schema import is_roman

SHARP = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
FLAT = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"]
MAJOR_NAMES = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
MINOR_NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "G♯", "A", "B♭", "B"]
_SHARP_MAJORS = {7, 2, 9, 4, 11, 6}          # major tonics whose signature uses sharps

NUMERALS = {"I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11}
DEGREES = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11}

_TOKEN = re.compile(
    r"^(?P<acc>♭|♯|b|#)?(?P<num>VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)"
    r"(?P<qual>maj|m|°|ø|\+)?(?P<ext>6|7|9|11|13)?(?P<suf>sus|alt|add9)?"
    r"(?:/(?P<bacc>♭|♯)?(?P<bass>[1-7]|VII|VI|IV|V|III|II|I))?$")
_KEY = re.compile(r"^\s*([A-Ga-g])\s*(♯|♭|#|b)?\s*(major|minor|maj|min|m)?\s*$", re.I)


class ChordError(ValueError):
    pass


def _acc(symbol: str | None) -> int:
    return {"♭": -1, "b": -1, "♯": 1, "#": 1}.get(symbol or "", 0)


def key_name(tonic: int, mode: str) -> str:
    names = MAJOR_NAMES if mode == "major" else MINOR_NAMES
    return f"{names[tonic % 12]} {mode}"


def parse_key(text: str) -> tuple[int, str]:
    """'F# minor', 'Ab major', 'C♯m', 'Bb' → (tonic pitch class, mode)."""
    m = _KEY.match(text or "")
    if not m:
        raise ChordError(f"Key must look like 'A♭ major' or 'F♯ minor', got '{text}'.")
    letter, acc, mode = m.groups()
    tonic = (SHARP.index(letter.upper()) + _acc(acc)) % 12
    mode = "minor" if (mode or "").lower() in ("minor", "min", "m") else "major"
    return tonic, mode


def prefers_flats(tonic: int, mode: str) -> bool:
    major = tonic if mode == "major" else (tonic + 3) % 12
    return major not in _SHARP_MAJORS


def split_progression(text: str) -> list[str]:
    """'ii9 – V13 – Imaj9' or 'ii9 V13 Imaj9' → tokens."""
    return [t for t in re.split(r"[\s,–—\-|]+", (text or "").strip()) if t]


def roman_root(token: str) -> int:
    """Semitones above the tonic of the chord's root."""
    m = _TOKEN.match(token)
    if not m:
        raise ChordError(f"'{token}' is not a Roman numeral")
    return (NUMERALS[m["num"].upper()] + _acc(m["acc"])) % 12


def realise(token: str, tonic: int, mode: str) -> str:
    """One Roman numeral in a key → a chord name, e.g. 'IV/V' in A♭ → 'D♭/E♭'."""
    m = _TOKEN.match(token)
    if not m or not is_roman(token):
        raise ChordError(f"'{token}' is not a Roman numeral")
    flats = prefers_flats(tonic, mode)
    if m["acc"] in ("♯", "#"):
        flats = False
    elif m["acc"] in ("♭", "b"):
        flats = True
    names = FLAT if flats else SHARP
    root = (tonic + roman_root(token)) % 12
    minor = m["num"].islower()
    qual, ext, suf = m["qual"] or "", m["ext"] or "", m["suf"] or ""

    if qual == "°":
        body = "dim7" if ext == "7" else "dim"
    elif qual == "ø":
        body = "m7♭5"
    elif qual == "+":
        body = "aug" + (ext if ext else "")
    elif qual == "maj":
        body = ("m" if minor else "") + "maj" + (ext or "7")
    elif minor or qual == "m":
        body = "m" + ext
    else:
        body = ext                      # bare 7/9/11/13 on an upper-case numeral is dominant
    if suf == "sus":
        body = (ext if not minor else body) + "sus4" if ext else "sus4"
    elif suf == "alt":
        body = "7alt"
    elif suf == "add9":
        body = ("m" if minor else "") + "add9"
    name = names[root] + body

    if m["bass"]:
        b = m["bass"]
        degree = DEGREES[b] if b.isdigit() else NUMERALS[b]
        bass = (tonic + degree + _acc(m["bacc"])) % 12
        if bass != root:
            name += "/" + names[bass]
    return name


def note_name(midi: float | None) -> str | None:
    if midi is None:
        return None
    n = int(round(midi))
    return f"{MINOR_NAMES[n % 12]}{n // 12 - 1}"
