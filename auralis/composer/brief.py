"""Song brief: what the prompt and lyrics ask for, in blueprint terms.

A deterministic keyword reader, not a language model. It only picks up what
the words clearly say ("92 BPM", "dark", "big chorus", "neo-soul", "no
bridge") and records each match, so the blueprint can say *which words* led
to a choice. Anything it does not recognise is left to Artist DNA and the
R&B Theory Atlas. Explicit settings (era, key, tempo...) always win over words.
"""
from __future__ import annotations

import re

from .chords import ChordError, parse_key

ERA_WORDS = [
    (r"quiet[\s-]*storm|\b80'?s\b|eighties", "80s_quiet_storm"),
    (r"neo[\s-]*soul", "neo_soul"),
    (r"\b70'?s\b|seventies|classic soul|old[\s-]*school soul", "70s_soul"),
    (r"\b90'?s\b|nineties|new jack", "90s_rnb"),
    (r"\b(2000'?s|00'?s|y2k|noughties)\b", "2000s_rnb"),
    (r"alt(ernative)?[\s-]*r&?b|modern r&?b|trap[\s-]*soul|\bpbr&?b", "modern_alt_rnb"),
]
HARMONY_WORDS = [
    (r"gospel|church", "gospel"), (r"jazz|lush|rich|extended", "rich"),
    (r"experimental|weird|ambiguous", "experimental"), (r"romantic|love|tender", "romantic"),
    (r"catchy|simple|familiar|pop", "familiar"), (r"\bdark|moody|sinister|brooding", "dark"),
]
VOCAL_WORDS = [
    (r"falsetto", "falsetto"), (r"\bruns?\b|melism", "melismatic"), (r"ad[\s-]*libs?", "adlib_heavy"),
    (r"conversational|talk[\s-]*sing|spoken", "conversational"), (r"belt|power ballad|powerful", "power_ballad"),
    (r"smooth|silky|soft vocal", "smooth"),
]
GROOVE_WORDS = [
    (r"laid[\s-]*back|behind the beat|lazy", "laid_back"), (r"pocket|funk", "deep_pocket"),
    (r"swing|shuffle", "swing"), (r"hip[\s-]*hop|boom[\s-]*bap|\btrap\b|808", "hiphop"),
    (r"straight|four on the floor", "straight"),
]
MINOR_WORDS = r"\b(dark|moody|sad|melanchol\w*|lonely|night|midnight|late[\s-]*night|heartbreak|blue|minor)\b"
MAJOR_WORDS = r"\b(bright|happy|uplifting|joyful|sunny|summer|major|celebrat\w*)\b"
SECTION_WORDS = {
    "intro": "intro", "verse": "verse", "pre-chorus": "pre-chorus", "prechorus": "pre-chorus",
    "pre chorus": "pre-chorus", "pre": "pre-chorus", "chorus": "chorus", "hook": "chorus",
    "refrain": "chorus", "bridge": "bridge", "outro": "outro", "interlude": "instrumental",
    "instrumental": "instrumental", "breakdown": "bridge",
}
_WORD = r"(intro|verse|pre[\s-]?chorus|pre|chorus|hook|refrain|bridge|outro|interlude|instrumental|breakdown)"
# A header is bracketed ("[Verse 1]", "(Chorus x2)") or the bare word ("Verse 2:").
_HEADER = re.compile(r"^\s*(?:[\[(]\s*" + _WORD + r"\b[^\])\n]*[\])]|" + _WORD + r"(?:\s*\d+)?\s*:?)\s*$", re.I)
# Songwriters often write the chords on the header line: "Chorus [F#m7 Em7 Am7]:" (Session 033).
_HEADER_CHORDS = re.compile(r"^\s*" + _WORD + r"(?:\s*\d+)?\s*[\[(]([^\])]*)[\])]\s*:?\s*$", re.I)
# Production notes written above or between the lyrics are read, not sung (Session 033):
# "90's R&B, A Minor, 77 bpm, electric piano, ...", "chords Emaj7 G#m7 ...", "70 bpm, Ab major".
_CHORD = re.compile(r"^[A-G][#b♭♯]?(?:m|maj|min|dim|aug|sus|add|M)?\d*(?:/[A-G][#b♭♯]?)?$")
_NOTE_STRONG = re.compile(r"\b\d{2,3}\s*bpm\b|\bbpm\s*\d{2,3}\b|\bkey of [a-g]\b|^\s*chords?\b", re.I)
_KEY_NAME = re.compile(r"\b[A-G][#b♭♯]?\s*(?:[Mm]ajor|[Mm]inor)\b")
_NOTE_TERMS = re.compile(r"\b(drums?|808s?|synths?|bass(?: guitar)?|guitars?|piano|keys|keyboards?|sax|saxophone|"
                         r"violins?|strings|percussion|rhodes|vocals|r&b|rnb|trap|hip[\s-]?hop|lo[\s-]?fi|neo[\s-]?soul|"
                         r"male|female|harmonies|ad[\s-]?libs|reverb|tempo)\b", re.I)
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "′": "'"})


def _is_note(line: str) -> bool:
    """A production note (tempo, key, chords, instrument or style tags), not a sung line."""
    tokens = re.findall(r"[^\s,\[\]():|-]+", line)
    if len(tokens) >= 2 and sum(bool(_CHORD.match(t)) for t in tokens) >= 0.7 * len(tokens):
        return True                                            # a chord chart: "Am C F G"
    if _NOTE_STRONG.search(line):
        return True
    commas = line.count(",")
    if _KEY_NAME.search(line) and (commas >= 2 or len(tokens) <= 5):
        return True
    items = [i.split() for i in line.split(",") if i.strip()]
    tag_list = commas >= 3 and sum(len(i) <= 3 for i in items) >= 0.7 * len(items)   # short tags, not phrases
    return tag_list and len(_NOTE_TERMS.findall(line)) >= 2


def _looks_like_chords(text: str) -> bool:
    tokens = [t for t in re.findall(r"[^\s,|-]+", text) if t.lower() not in ("chords", "chord", "key")]
    return bool(tokens) and sum(bool(_CHORD.match(t)) for t in tokens) >= 0.5 * len(tokens)


def lyric_notes(lyrics: str) -> list[str]:
    """The production-note lines in pasted lyrics, and the chords written on headers."""
    out = []
    for raw in (lyrics or "").splitlines():
        line = raw.strip().translate(_QUOTES)
        m = _HEADER_CHORDS.match(line)
        if m:
            label = "chords" if _looks_like_chords(m.group(2)) else "note"
            out.append(f"{m.group(1)} {label}: {m.group(2).strip()}")
        elif line and not _HEADER.match(line) and _is_note(line):
            out.append(line)
    return out


def _first(patterns, text):
    for pattern, value in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return value, m.group(0).strip()
    return None, None


def parse_lyrics(lyrics: str) -> list[dict]:
    """Split lyrics on section headers ('[Verse 1]', 'Chorus:'). Lines before
    any header form one untyped block. Returns [{type, lines}]."""
    blocks: list[dict] = []
    current = None
    for raw in (lyrics or "").splitlines():
        line = raw.strip().translate(_QUOTES)              # curly don’t -> don't (else sung "don" + "t")
        m = _HEADER.match(line)
        chords = None if m else _HEADER_CHORDS.match(line)
        if m or chords:
            name = (m.group(1) or m.group(2)) if m else chords.group(1)
            word = re.sub(r"[\s-]+", " ", name.lower()).replace("pre chorus", "pre-chorus")
            current = {"type": SECTION_WORDS.get(word, SECTION_WORDS.get(word.replace(" ", ""), "verse")),
                       "lines": []}
            if chords:
                written = chords.group(2).strip()
                current["written_chords" if _looks_like_chords(written) else "header_note"] = written
            blocks.append(current)
            continue
        if not line or _is_note(line):                       # production notes are read, not sung
            continue
        if current is None:
            current = {"type": None, "lines": []}
            blocks.append(current)
        current["lines"].append(line)
    return blocks


def parse_brief(prompt: str = "", lyrics: str = "", **settings) -> dict:
    """Read the prompt and lyrics. ``settings`` (era, harmony, vocal, groove,
    key, tempo, length_seconds, bridge, chorus_emphasis) override the words."""
    # production notes in the lyrics box ("77 bpm, A minor, 90's R&B") are heard like the prompt
    text = " ".join([prompt or ""] + lyric_notes(lyrics)).strip()
    heard: list[dict] = []

    def hear(field, value, words):
        if value is not None:
            heard.append({"field": field, "value": value, "words": words})
        return value

    era = hear("era", *_first(ERA_WORDS, text))
    harmony = hear("harmony", *_first(HARMONY_WORDS, text))
    vocal = hear("vocal", *_first(VOCAL_WORDS, text))
    groove = hear("groove", *_first(GROOVE_WORDS, text))

    tempo = None
    m = re.search(r"(\d{2,3})\s*(bpm|beats)", text, re.I)
    if m and 40 <= int(m.group(1)) <= 220:
        tempo = hear("tempo", int(m.group(1)), m.group(0))
    feel = None
    m = re.search(r"slow[\s-]*jam|ballad|\bslow\b|downtempo", text, re.I)
    if m:
        feel = hear("tempo_feel", "slow", m.group(0))
    else:
        m = re.search(r"up[\s-]*tempo|\bfast\b|danceable|dance|bouncy|club", text, re.I)
        if m:
            feel = hear("tempo_feel", "fast", m.group(0))
        else:
            m = re.search(r"mid[\s-]*tempo", text, re.I)
            if m:
                feel = hear("tempo_feel", "mid", m.group(0))

    key = mode = None
    m = re.search(r"\bin\s+([A-G](?:♯|♭|#|b)?\s*(?:major|minor|maj|min|m)?)\b", text) or \
        re.search(r"\b([A-G](?:♯|♭|#|b)?\s*(?:major|minor))\b", text)
    if m:
        try:
            tonic, mode = parse_key(m.group(1))
            key = hear("key", {"tonic": tonic, "mode": mode}, m.group(0))
        except ChordError:
            pass
    if mode is None:
        mm = re.search(MINOR_WORDS, text, re.I)
        mj = re.search(MAJOR_WORDS, text, re.I)
        if mm and not mj:
            mode = hear("mode", "minor", mm.group(0))
        elif mj and not mm:
            mode = hear("mode", "major", mj.group(0))

    length = None
    m = re.search(r"(\d):([0-5]\d)", text)
    if m:
        length = hear("length_seconds", int(m.group(1)) * 60 + int(m.group(2)), m.group(0))
    else:
        m = re.search(r"(\d(?:\.\d)?)\s*(?:min|minutes?)\b", text, re.I)
        if m:
            length = hear("length_seconds", int(float(m.group(1)) * 60), m.group(0))
        else:
            m = re.search(r"\bshort\b|radio edit|snippet", text, re.I)
            if m:
                length = hear("length_seconds", 150, m.group(0))
            else:
                m = re.search(r"\blong\b|extended|epic", text, re.I)
                if m:
                    length = hear("length_seconds", 270, m.group(0))

    bridge = None
    m = re.search(r"no bridge|without (a )?bridge", text, re.I)
    if m:
        bridge = hear("bridge", False, m.group(0))
    elif (m := re.search(r"\bbridge\b", text, re.I)):
        bridge = hear("bridge", True, m.group(0))
    chorus = None
    m = re.search(r"(big|huge|massive|anthemic|soaring) (chorus|hook)", text, re.I)
    if m:
        chorus = hear("chorus_emphasis", True, m.group(0))

    blocks = parse_lyrics(lyrics)
    brief = {
        "prompt": prompt or "", "era": era, "harmony": harmony, "vocal": vocal, "groove": groove,
        "tempo": tempo, "tempo_feel": feel, "key": key, "mode": mode, "length_seconds": length,
        "bridge": bridge, "chorus_emphasis": bool(chorus),
        "lyrics": lyrics or "", "lyric_sections": blocks,
        "heard": heard, "set_by_you": [],
    }
    for field, value in settings.items():
        if value in (None, ""):
            continue
        if field == "key":
            tonic, mode = parse_key(value)
            brief["key"], brief["mode"] = {"tonic": tonic, "mode": mode}, mode
        elif field in brief:
            brief[field] = value
        else:
            continue
        brief["set_by_you"].append(field)
    return brief
