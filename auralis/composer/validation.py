"""Blueprint validation: errors block a revision, warnings are shown."""
from __future__ import annotations

from ..theory.schema import FORBIDDEN_KEYS, is_roman
from .chords import _TOKEN, ChordError, parse_key

SECTION_TYPES = ("intro", "verse", "pre-chorus", "chorus", "bridge", "instrumental", "outro")
LEVELS = ("off", "light", "medium", "full")
MAX_SECONDS = 12 * 60


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            yield p, k
            yield from _walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def validate_blueprint(bp: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    tempo = bp.get("tempo")
    if not isinstance(tempo, (int, float)) or not 40 <= tempo <= 220:
        errors.append("Tempo must be between 40 and 220 BPM.")
    if bp.get("meter") != "4/4":
        errors.append("Only 4/4 is supported for now.")
    try:
        _, mode = parse_key(bp.get("key", ""))
    except ChordError as exc:
        errors.append(str(exc))
        mode = None

    sections = bp.get("sections") or []
    if not sections:
        errors.append("A blueprint needs at least one section.")
    for s in sections:
        label = s.get("label") or s.get("type")
        if s.get("type") not in SECTION_TYPES:
            errors.append(f"{label}: unknown section type '{s.get('type')}'.")
        bars = s.get("bars")
        if not isinstance(bars, int) or not 1 <= bars <= 64:
            errors.append(f"{label}: bars must be a whole number from 1 to 64.")
        e = s.get("energy")
        if not isinstance(e, (int, float)) or not 0 <= e <= 1:
            errors.append(f"{label}: energy must be between 0 and 1.")
        if s.get("chords_per_bar") not in (0.25, 0.5, 1, 1.0, 2, 2.0):
            errors.append(f"{label}: chords per bar must be ¼, ½, 1 or 2.")
        roman = (s.get("progression") or {}).get("roman") or []
        if not roman:
            errors.append(f"{label}: needs at least one chord.")
        bad = [t for t in roman if not is_roman(t)]
        if bad:
            errors.append(f"{label}: {', '.join(bad)} {'is' if len(bad) == 1 else 'are'} not Roman numerals "
                          "(write degrees like ii9, IV/V, ♭VImaj7).")
        if len(roman) > 16:
            errors.append(f"{label}: at most 16 chords per section progression.")
        for role, level in (s.get("arrangement") or {}).items():
            if level not in LEVELS:
                errors.append(f"{label}: {role} level must be one of {', '.join(LEVELS)}.")
        v = s.get("vocal")
        vr = (bp.get("vocal") or {})
        if v and vr.get("range_high_midi") is not None and v["peak_midi"] > vr["range_high_midi"] - 1:
            warnings.append(f"{label}: the peak {v['peak']} is at the top of your range.")
        if isinstance(bars, int) and s.get("lyrics") and len(s["lyrics"]) > bars:
            warnings.append(f"{label}: {len(s['lyrics'])} lyric lines in {bars} bars will feel crowded.")

    if mode:
        for s in sections:
            roman = (s.get("progression") or {}).get("roman") or []
            first = _TOKEN.match(roman[0]) if roman else None
            tonic = {"minor": "I", "major": "i"}[mode]
            if first and first["num"] == tonic and not first["acc"]:
                warnings.append(f"{s.get('label')}: starts on {roman[0]} in a {mode} key; the chords are "
                                "realised literally, as borrowed colour.")
    if bp.get("duration_seconds") and bp["duration_seconds"] > MAX_SECONDS:
        errors.append("The song is longer than 12 minutes.")

    for path, key in _walk({k: v for k, v in bp.items() if k != "lyrics"}):
        if key.lower() in FORBIDDEN_KEYS and path not in ("lyrics",) and not path.endswith(".lyrics"):
            errors.append(f"{path}: '{key}' is not allowed in a blueprint (no melodies or transcriptions).")
    for chk in (bp.get("originality") or {}).get("checks", []):
        if chk["status"] == "flag":
            warnings.append(f"Originality: {chk['label']}. {chk['detail']}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}
