"""Song memory / retrieval (AU-12, roadmap §4): which of my songs should shape this one?

For a request (tempo, mode, key family, energy, groove, or songs the user
picked), rank the switched-on catalog songs by musical closeness and return
3–8 of them with the reasons. Those songs' *traits* (never their audio or
melody) then steer the blueprint: ``build_dna`` over just that subset gives a
focused Artist DNA ("continue my sound from these songs").
"""
from __future__ import annotations

import numpy as np

from .dna import _signature


def _tempo_gap(a: float, b: float) -> float:
    """BPM distance allowing the half/double-time reading (AU-02 finding)."""
    return min(abs(a - b), abs(a - 2 * b), abs(2 * a - b))


def features(analysis: dict) -> dict:
    g, t, k = analysis["global"], analysis["tempo"], analysis["key"]
    st = analysis.get("structure", {})
    choruses = [s for s in st.get("sections", []) if s.get("role_guess") == "chorus"]
    verses = [s for s in st.get("sections", []) if s.get("role_guess") == "verse"]
    lift = (np.mean([s["energy"] for s in choruses]) - np.mean([s["energy"] for s in verses])
            if choruses and verses else None)
    return {"bpm": t["bpm"], "mode": k["mode"], "family": _signature(k["tonic"], k["mode"])[0],
            "syncopation": analysis["rhythm"]["syncopation"], "lufs": g["integrated_lufs"],
            "width": g["stereo_width"], "low_ratio": analysis["production"]["low_ratio"],
            "chorus_lift": lift, "changes_per_bar": analysis["harmony"]["changes_per_bar"]}


def retrieve(target: dict, songs: list, analyses: dict, n: int = 5, picked: list[str] | None = None) -> list[dict]:
    """Rank songs for ``target`` = {bpm?, mode?, family?, syncopation?, chorus_lift?}.

    Songs the user picked always come first. Returns [{song_id, title, score, reasons}].
    """
    picked = picked or []
    ranked = []
    for s in songs:
        a = analyses.get(s.id)
        if not a or not s.included or s.analysis_status != "done":
            continue
        f = features(a)
        score, why = 0.0, []
        if target.get("bpm"):
            gap = _tempo_gap(f["bpm"], target["bpm"])
            score += max(0.0, 1.0 - gap / 20.0)
            if gap <= 5:
                why.append(f"tempo {f['bpm']:.0f} BPM")
        if target.get("mode"):
            if f["mode"] == target["mode"]:
                score += 0.6
                why.append(f"{f['mode']} key")
        if target.get("family") is not None and f["family"] == target["family"]:
            score += 0.5
            why.append("same key family")
        if target.get("syncopation") is not None:
            d = abs(f["syncopation"] - target["syncopation"])
            score += max(0.0, 0.4 - d)
            if d < 0.1:
                why.append("similar groove")
        if target.get("chorus_lift") is not None and f["chorus_lift"] is not None:
            d = abs(f["chorus_lift"] - target["chorus_lift"])
            score += max(0.0, 0.3 - d)
            if d < 0.1:
                why.append("similar chorus lift")
        if s.kind == "stem-set":
            score += 0.15                     # separated stems → more reliable traits (AU-02)
        if s.id in picked:
            score += 10.0
            why.insert(0, "you picked it")
        ranked.append({"song_id": s.id, "title": s.title, "score": round(score, 3), "reasons": why or ["closest overall"]})
    ranked.sort(key=lambda r: -r["score"])
    return ranked[: max(1, n)]


def focused_dna(song_ids: list[str], songs: list, analyses: dict, voice=None) -> dict:
    """Artist DNA from just these songs (retrieval → blueprint)."""
    from .dna import build_dna

    chosen = [s for s in songs if s.id in set(song_ids)]
    dna = build_dna(chosen, analyses, voice)
    dna.setdefault("method", {})["focused_on"] = [s.id for s in chosen]
    return dna
