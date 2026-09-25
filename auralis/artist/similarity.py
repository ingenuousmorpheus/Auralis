"""Similarity / originality guard (AU-12, roadmap §12): sounds like me ≠ copies my old song.

Compares a blueprint and its melody guide with the user's own catalog:

* **harmony**  the blueprint's chord per bar (reduced to Roman-numeral triads, so
               colour doesn't hide a copy) against every song's analysed chords per
               bar: the longest run of identical bars. Common loops are shared by
               many songs, so a short shared run is normal; a long one is flagged.
* **melody**   the melody guide's interval sequence (transposition-free) against the
               lead-vocal melodies of the closest catalog songs, extracted on demand
               with the library's own note reader and cached locally. A long run of
               identical intervals (with real melodic shape, not repeated notes) is
               flagged.
* **audio**    not compared yet: the render is synthesized from the blueprint, so
               harmony and melody are where copying could come from. Noted honestly.

Catalog melodies are cached under ``%LOCALAPPDATA%/Auralis/artist/melodies``, never in the repo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

HARMONY_FLAG_BARS = 16        # a verse + chorus of identical bars
HARMONY_NOTE_BARS = 8
MELODY_FLAG_INTERVALS = 8     # nine notes in a row with the same intervals
MELODY_NOTE_INTERVALS = 6
_TRIAD = re.compile(r"^(♭|♯|b|#)?(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)")


def reduce_roman(token: str) -> str:
    m = _TRIAD.match(token or "")
    return (m.group(1) or "").replace("b", "♭").replace("#", "♯") + m.group(2) if m else "N"


def blueprint_bars(bp: dict) -> list[str]:
    """One reduced chord per bar (the chord sounding on beat 1)."""
    out = []
    for s in bp["sections"]:
        chords = s.get("chords") or []
        for bar in range(1, int(s["bars"]) + 1):
            c = next((c for c in reversed(chords) if (c["bar"], c["beat"]) <= (bar, 1)), None)
            out.append(reduce_roman(c["roman"]) if c else "N")
    return out


def longest_common_run(a: list, b: list, ignore=("N",)) -> tuple[int, int, int]:
    """(length, start in a, start in b) of the longest identical contiguous run."""
    best = (0, 0, 0)
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1] and a[i - 1] not in ignore:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best[0]:
                    best = (cur[j], i - cur[j], j - cur[j])
        prev = cur
    return best


def harmony_check(bp: dict, catalog: list[dict]) -> dict:
    """``catalog``: [{song_id, title, roman_per_bar}]."""
    bars = blueprint_bars(bp)
    hits = []
    for song in catalog:
        other = [reduce_roman(t) for t in song.get("roman_per_bar") or []]
        run, i, j = longest_common_run(bars, other)
        if run >= HARMONY_NOTE_BARS:
            hits.append({"song_id": song["song_id"], "title": song.get("title"), "bars": run,
                         "at_bar": i + 1, "their_bar": j + 1})
    hits.sort(key=lambda h: -h["bars"])
    worst = hits[0]["bars"] if hits else 0
    status = "flag" if worst >= HARMONY_FLAG_BARS else "info" if hits else "pass"
    detail = ("No run of 8+ identical bars with any of your songs." if not hits else
              f"Longest shared chord run: {worst} bars with “{hits[0]['title']}” (bar {hits[0]['at_bar']})."
              + (" Regenerate the chords of that section to keep this song distinct." if status == "flag" else
                 " Short shared loops are normal in R&B."))
    return {"id": "catalog_harmony", "label": "Chords differ from each of your songs", "status": status,
            "detail": detail, "hits": hits[:5], "bars_checked": len(bars)}


def _intervals(midis: list[float]) -> list[int]:
    notes = [int(round(m)) for m in midis]
    return [b - a for a, b in zip(notes, notes[1:]) if abs(b - a) <= 12]


def _has_shape(run: list[int]) -> bool:
    """A distinctive phrase, not just steps: 3+ different intervals, a skip or leap,
    and not mostly repeated notes."""
    return (len(set(run)) >= 3 and any(abs(x) >= 3 for x in run)
            and sum(1 for x in run if x == 0) <= len(run) // 2)


def chance_run(ours: list[int], theirs: list[int], shuffles: int = 16, seed: int = 7) -> int:
    """The longest shared run expected by chance: 95th percentile over shuffled
    copies of ``theirs`` (same notes, random order). Real interval alphabets are
    small (mostly steps), so chance runs of 6–11 intervals are normal (AU-12 finding)."""
    import random

    rng = random.Random(seed)
    runs = []
    for _ in range(shuffles):
        sh = theirs[:]
        rng.shuffle(sh)
        runs.append(longest_common_run(ours, sh, ignore=())[0])
    return int(np.percentile(runs, 95)) if runs else 0


def melody_check(melody_notes: list, catalog_melodies: list[dict]) -> dict:
    """``melody_notes``: [(start_beat, length, midi, vel)]; catalog: [{song_id, title, midis}]."""
    ours = _intervals([n[2] for n in sorted(melody_notes)])
    hits = []
    for song in catalog_melodies:
        theirs = _intervals(song.get("midis") or [])
        run, i, j = longest_common_run(ours, theirs, ignore=())
        if run < MELODY_NOTE_INTERVALS:
            continue
        chance = chance_run(ours, theirs)
        shaped = _has_shape(ours[i:i + run])
        # a copy = clearly longer than chance AND a real melodic shape
        level = "flag" if shaped and run >= max(MELODY_FLAG_INTERVALS, chance + 3) else             "info" if shaped and run > chance else None
        if level:
            hits.append({"song_id": song["song_id"], "title": song.get("title"), "intervals": run,
                         "chance": chance, "level": level})
    hits.sort(key=lambda h: (h["level"] != "flag", -h["intervals"]))
    worst = hits[0]["intervals"] if hits else 0
    status = hits[0]["level"] if hits else "pass"
    checked = len(catalog_melodies)
    detail = (f"Compared with {checked} of your lead vocals: no shared phrase beyond what chance produces." if not hits else
              f"{worst + 1} notes in a row follow the same intervals as “{hits[0]['title']}” "
              f"(chance level about {hits[0]['chance'] + 1})."
              + (" Make a new take (new seed) to rewrite the melody." if status == "flag" else ""))
    if not checked:
        detail = "None of your songs has a separated lead vocal to compare with."
    return {"id": "catalog_melody", "label": "Melody differs from each of your songs", "status": status,
            "detail": detail, "hits": hits[:5], "songs_compared": checked}


# ── catalog melodies (cached) ───────────────────────────────────────────────

def catalog_melody(library, song) -> list[float] | None:
    """Lead-vocal note pitches for a stem-set song, extracted once and cached."""
    from .analyze import _to_rate, melody_notes
    from .library import SongAudio

    cache_dir = Path(library.root) / "melodies"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{song.id}.json"
    fingerprint = song.fingerprint
    if cache.is_file():
        data = json.loads(cache.read_text("utf-8"))
        if data.get("fingerprint") == fingerprint:
            return data["midis"]
    if not any(f.role == "lead_vocal" for f in song.files):
        return None
    mix, sr, stems = SongAudio(song).load()
    lead = stems.get("lead_vocal")
    midis = None
    if lead is not None and np.max(np.abs(lead)) > 1e-3:
        got = melody_notes(_to_rate(lead, sr, target=16000))
        if got:
            midis = [round(n[2], 2) for n in got[0]]
    cache.write_text(json.dumps({"fingerprint": fingerprint, "midis": midis}), encoding="utf-8")
    return midis
