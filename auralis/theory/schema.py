"""Validation for the R&B Theory Atlas, including the copyright boundary.

The Atlas stores *relationships and distributions* (Roman numerals, chord
qualities, contour classes, tempo bands, timing offsets), never material that
could reproduce a specific song: no melodies, note sequences, MIDI, lyrics or
audio. ``validate_atlas`` enforces that on every load, so a bad row fails loudly
instead of quietly becoming a generation template.

This is an engineering risk-reduction rule, not legal advice.
"""
from __future__ import annotations

import re

STATUSES = {"sourced", "hypothesis"}
ERA_IDS = {"70s_soul", "80s_quiet_storm", "90s_rnb", "neo_soul", "2000s_rnb", "modern_alt_rnb"}
HARMONY_COLORS = {"familiar", "rich", "gospel", "dark", "romantic", "experimental"}
VOCAL_APPROACHES = {"smooth", "conversational", "melismatic", "falsetto", "power_ballad", "adlib_heavy"}
GROOVE_FEELS = {"straight", "laid_back", "deep_pocket", "swing", "hiphop"}

# Keys that would carry reproducible musical material. Never allowed anywhere.
FORBIDDEN_KEYS = {"melody", "notes", "note_sequence", "midi", "lyrics", "lyric", "audio",
                  "transcription", "pitches", "onsets"}
MAX_PROGRESSION = 8        # longer chord strings start to look like transcriptions

_ROMAN = re.compile(
    r"^(♭|♯|b|#)?(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)"
    r"(maj|m|°|ø|\+)?(6|7|9|11|13)?(sus|alt|add9)?(/(♭|♯)?(1|2|3|4|5|6|7|VII|VI|IV|V|III|II|I))?$")


class AtlasError(ValueError):
    pass


def is_roman(token: str) -> bool:
    return bool(_ROMAN.match(token))


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}" if path else k, k
            yield from _walk_keys(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def validate_atlas(data: dict) -> list[str]:
    """Return a list of problems (empty when valid)."""
    problems: list[str] = []

    for path, key in _walk_keys(data):
        if key.lower() in FORBIDDEN_KEYS:
            problems.append(f"{path}: '{key}' could carry reproducible material and is not allowed")

    source_ids = {s["id"] for s in data.get("sources", [])}

    def check_common(kind, row, need_eras=True):
        rid = row.get("id") or row.get("quality") or "?"
        if row.get("status") not in STATUSES:
            problems.append(f"{kind} {rid}: status must be one of {sorted(STATUSES)}")
        srcs = row.get("sources") or []
        if not srcs:
            problems.append(f"{kind} {rid}: needs at least one source")
        for s in srcs:
            if s not in source_ids:
                problems.append(f"{kind} {rid}: unknown source '{s}'")
        if row.get("status") == "sourced" and srcs == ["auralis_editorial"]:
            problems.append(f"{kind} {rid}: 'sourced' needs a source other than the editorial placeholder")
        if need_eras:
            eras = row.get("eras") or []
            eras = list(eras) if isinstance(eras, list) else list(eras.keys())
            for e in eras:
                if e not in ERA_IDS:
                    problems.append(f"{kind} {rid}: unknown era '{e}'")

    for era in data.get("eras", []):
        if era.get("id") not in ERA_IDS:
            problems.append(f"era {era.get('id')}: unknown era id")
        lo, hi = era.get("bpm_band", [0, 0])
        if not 30 <= lo < hi <= 220:
            problems.append(f"era {era.get('id')}: bpm_band looks wrong")
        check_common("era", era, need_eras=False)

    for fam in data.get("progression_families", []):
        check_common("progression", fam)
        roman = fam.get("roman") or []
        if not 2 <= len(roman) <= MAX_PROGRESSION:
            problems.append(f"progression {fam.get('id')}: 2 to {MAX_PROGRESSION} chords, got {len(roman)}")
        for token in roman:
            if not is_roman(token):
                problems.append(f"progression {fam.get('id')}: '{token}' is not a Roman numeral (no absolute chord names)")
        for c in fam.get("harmony_colors", []):
            if c not in HARMONY_COLORS:
                problems.append(f"progression {fam.get('id')}: unknown harmony colour '{c}'")
        if fam.get("mode") not in ("major", "minor"):
            problems.append(f"progression {fam.get('id')}: mode must be major or minor")

    for chord in data.get("chord_vocabulary", []):
        check_common("chord", chord)

    for vp in data.get("vocal_patterns", []):
        check_common("vocal pattern", vp)
        for a in vp.get("approach", []):
            if a not in VOCAL_APPROACHES:
                problems.append(f"vocal pattern {vp.get('id')}: unknown approach '{a}'")
        # Only anchor degrees are allowed, never a line of notes.
        for field in ("start_degree", "end_degree", "peak_degree"):
            if isinstance(vp.get(field), list):
                problems.append(f"vocal pattern {vp.get('id')}: {field} must be one anchor, not a sequence")

    for g in data.get("grooves", []):
        check_common("groove", g)
        if g.get("feel") not in GROOVE_FEELS:
            problems.append(f"groove {g.get('id')}: unknown feel '{g.get('feel')}'")

    for lift in data.get("section_lift", []):
        check_common("section lift", lift)

    for ev in data.get("evidence", []):
        check_common("evidence", ev, need_eras=False)
        for token in (ev.get("abstraction") or {}).get("roman", []):
            if not is_roman(token):
                problems.append(f"evidence {ev.get('id')}: '{token}' is not a Roman numeral")
        if len((ev.get("abstraction") or {}).get("roman", [])) > MAX_PROGRESSION:
            problems.append(f"evidence {ev.get('id')}: abstraction too long to be abstract")

    return problems
