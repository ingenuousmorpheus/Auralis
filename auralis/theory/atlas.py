"""R&B Theory Atlas: retrieve era-appropriate, transposable candidates.

Given an era (and optional section, harmony colour, vocal approach, groove
feel), return several documented options, each with its provenance, rather
than one "correct" answer. Keys are chosen last, from the singer's range and
the artist's own key-family habits, never from "what key hits are in".

No melody is produced or stored here. See ``schema.py`` for the boundary.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .schema import AtlasError, validate_atlas

DATA = Path(__file__).parent / "data" / "rnb_atlas.json"
KEY_NAMES = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]


@lru_cache(maxsize=4)
def _load(path: str = str(DATA)) -> dict:
    data = json.loads(Path(path).read_text("utf-8"))
    problems = validate_atlas(data)
    if problems:
        raise AtlasError("R&B Atlas failed validation:\n" + "\n".join(problems))
    return data


def load_atlas(path: str | Path | None = None) -> dict:
    return _load(str(path or DATA))


def eras(atlas: dict | None = None) -> list[dict]:
    atlas = atlas or load_atlas()
    return [{"id": e["id"], "name": e["name"], "bpm_band": e["bpm_band"], "status": e["status"]}
            for e in atlas["eras"]]


def _sources(atlas: dict, ids: list[str]) -> list[dict]:
    by_id = {s["id"]: s for s in atlas["sources"]}
    return [{"id": i, "title": by_id[i]["title"], "url": by_id[i]["url"]} for i in ids]


def candidates(
    era: str,
    section: str | None = None,
    harmony: str | None = None,
    vocal: str | None = None,
    groove: str | None = None,
    n: int = 3,
    voice_range: tuple[float, float] | None = None,
    dna_key_families: list[int] | None = None,
    atlas: dict | None = None,
) -> dict:
    """Several candidates per dimension for one era, each with sources.

    ``voice_range`` is (low, high) in MIDI; ``dna_key_families`` are the major
    tonics (pitch classes) of the artist's most-used key signatures.
    """
    atlas = atlas or load_atlas()
    era_row = next((e for e in atlas["eras"] if e["id"] == era), None)
    if era_row is None:
        raise KeyError(f"Unknown era: {era}")

    def score_prog(p):
        s = p["eras"].get(era, 0.0)
        if section and section in p["sections"]:
            s += 0.3
        if harmony and harmony in p["harmony_colors"]:
            s += 0.4
        return s

    progs = sorted((p for p in atlas["progression_families"] if p["eras"].get(era)),
                   key=lambda p: (-score_prog(p), p["id"]))[:n]
    harmony_out = []
    for p in progs:
        keys = suggest_keys(p["mode"], voice_range, dna_key_families)
        harmony_out.append({
            "id": p["id"], "name": p["name"], "roman": p["roman"], "mode": p["mode"], "loop": p["loop"],
            "cadence": p["cadence"], "tension": p["tension"], "sections": p["sections"],
            "comment": p["comment"], "reharm": p["reharm"], "era_affinity": p["eras"][era],
            "status": p["status"], "sources": _sources(atlas, p["sources"]),
            "keys": keys,
        })

    def rank(rows, field, want):
        return sorted(rows, key=lambda r: (-(want in r.get(field, [])) if want else 0, r["id"]))

    vocal_rows = [v for v in atlas["vocal_patterns"] if era in v["eras"]]
    if section:
        vocal_rows.sort(key=lambda v: v["section"] != section)
    vocal_rows = rank(vocal_rows, "approach", vocal)[:n]
    groove_rows = [g for g in atlas["grooves"] if era in g["eras"]]
    if groove:
        groove_rows.sort(key=lambda g: g["feel"] != groove)
    groove_rows = groove_rows[:n]
    lifts = [l for l in atlas["section_lift"] if era in l["eras"]]
    colors = [c for c in atlas["chord_vocabulary"] if era in c["eras"]]

    strip = lambda r: {k: v for k, v in r.items() if k not in ("sources", "eras")} | \
        {"sources": _sources(atlas, r["sources"])}
    return {
        "era": {k: era_row[k] for k in ("id", "name", "bpm_band", "harmonic_rhythm", "traits", "status")}
               | {"sources": _sources(atlas, era_row["sources"])},
        "harmony": harmony_out,
        "vocal": [strip(v) for v in vocal_rows],
        "groove": [strip(g) for g in groove_rows],
        "section_lift": [strip(l) for l in lifts],
        "chord_colors": [c["quality"] for c in colors],
        "originality": "Roman-numeral and descriptor abstractions only; no melody, lyrics or transcription.",
    }


def key_fit(tonic: int, voice_range: tuple[float, float]) -> tuple[float, float, int]:
    """(stretch, margin, tonic MIDI note) for the best octave of ``tonic``.

    The lead spans tonic - 5 to tonic + 14 and wants a semitone of headroom;
    ``stretch`` is how far that span leaves the range (0 when it fits).
    """
    low, high = voice_range
    best = None
    for octave in (2, 3, 4):
        t = 12 * (octave + 1) + tonic
        span_low, peak = t - 5, t + 14
        stretch = max(0.0, low - span_low) + max(0.0, peak - (high - 1))
        margin = min(span_low - low, high - 1 - peak)
        if best is None or (stretch, -margin) < (best[0], -best[1]):
            best = (stretch, margin, t)
    return best


def suggest_keys(mode: str, voice_range: tuple[float, float] | None,
                 dna_key_families: list[int] | None = None, n: int = 3) -> list[dict]:
    """Rank keys for a progression by voice fit, then by the artist's key habits.

    Voice-fit rule (transparent and adjustable): the lead spans from the
    dominant below the tonic up to the octave, and the chorus peaks a step
    above that (tonic - 5 to tonic + 14, 19 semitones). A key fits when that
    span sits inside the singer's range with a semitone of headroom on top.
    When no key fits cleanly, keys are ranked by how little they stretch the
    range, and the answer says so rather than returning nothing.
    """
    results = []
    for tonic in range(12):
        reasons, score = [], 0.0
        if voice_range:
            stretch, margin, _ = key_fit(tonic, voice_range)
            if stretch == 0:
                score += 1.0 + min(margin, 4) * 0.1
                reasons.append(f"verse and chorus peak fit your range with {margin:.0f} semitone(s) to spare")
            else:
                score += max(0.0, 0.8 - 0.15 * stretch)
                reasons.append(f"stretches your range by {stretch:.1f} semitone(s)")
        major_tonic = tonic if mode == "major" else (tonic + 3) % 12
        if dna_key_families and major_tonic in dna_key_families:
            rank = dna_key_families.index(major_tonic)
            score += 0.6 - 0.1 * rank
            reasons.append("a key family you use often")
        if not voice_range and not dna_key_families:
            reasons.append("no voice range yet; any key works")
        results.append({"key": f"{KEY_NAMES[tonic]} {mode}", "tonic": tonic, "score": round(score, 2),
                        "why": "; ".join(reasons)})
    results.sort(key=lambda r: (-r["score"], r["tonic"]))
    return results[:n]
