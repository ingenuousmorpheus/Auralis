"""AU-12 retrieval + similarity guard (synthetic catalogs; no catalog audio)."""
from types import SimpleNamespace

import numpy as np
import pytest

from auralis.artist.retrieval import focused_dna, retrieve
from auralis.artist.similarity import (blueprint_bars, harmony_check, longest_common_run, melody_check,
                                       reduce_roman)
from auralis.composer import build_blueprint, revise
from auralis.composer.arrange import arrange

VOICE = (50.0, 72.0)


def _analysis(bpm, tonic, mode, sync=0.4, roman=None):
    return {
        "global": {"integrated_lufs": -14.0, "stereo_width": 0.3, "duration_seconds": 180, "loudness_range_lu": 6.0},
        "tempo": {"bpm": bpm}, "key": {"tonic": tonic, "mode": mode, "name": f"{tonic} {mode}"},
        "rhythm": {"syncopation": sync, "onsets_per_beat": 2.0, "swing_position": 0.5, "source": "drums stem"},
        "production": {"low_ratio": 0.6, "vocal_to_music_db": -6.0},
        "harmony": {"changes_per_bar": 1.0, "diatonic_share": 0.9, "top_progressions": [], "vocabulary": {},
                    "roman_per_bar": roman or []},
        "structure": {"sections": [], "roles_form": ""}, "energy": {"per_bar": []}, "melody": None,
    }


def _song(i, title, kind="stem-set", included=True):
    return SimpleNamespace(id=f"{i:012x}", title=title, kind=kind, variants=[], included=included,
                           analysis_status="done", files=[])


def test_reduce_and_run():
    assert reduce_roman("♭VImaj7") == "♭VI" and reduce_roman("i9") == "i" and reduce_roman("IV/V") == "IV"
    assert longest_common_run(list("abcdxyz"), list("zzabcdq")) == (4, 0, 2)
    assert longest_common_run(["N", "N"], ["N", "N"]) == (0, 0, 0)


def test_retrieval_ranks_by_closeness_and_honours_picks():
    songs = [_song(1, "Close Minor"), _song(2, "Far Major", kind="mix"), _song(3, "Half Time"),
             _song(4, "Switched Off", included=False)]
    analyses = {songs[0].id: _analysis(92, 9, "minor"), songs[1].id: _analysis(140, 0, "major"),
                songs[2].id: _analysis(184, 9, "minor"), songs[3].id: _analysis(92, 9, "minor")}
    ranked = retrieve({"bpm": 92, "mode": "minor"}, songs, analyses, n=3)
    ids = [r["song_id"] for r in ranked]
    assert ids[0] == songs[0].id and songs[3].id not in ids                  # switched-off songs never count
    assert ids.index(songs[2].id) < ids.index(songs[1].id)                   # 184 reads as double-time 92
    assert "tempo 92 BPM" in ranked[0]["reasons"]
    picked = retrieve({"bpm": 92}, songs, analyses, n=2, picked=[songs[1].id])
    assert picked[0]["song_id"] == songs[1].id and picked[0]["reasons"][0] == "you picked it"


def test_focused_dna_uses_only_those_songs():
    songs = [_song(1, "Alpha Song"), _song(2, "Beta Tune")]
    analyses = {songs[0].id: _analysis(80, 9, "minor"), songs[1].id: _analysis(120, 0, "major")}
    full = {s.id: a | {"structure": {"sections": [], "roles_form": ""}} for s, a in zip(songs, analyses.values())}
    for s in songs:
        s.analysis_status = "done"
    dna = focused_dna([songs[0].id], songs, full)
    assert dna["method"]["songs_used"] == 1 and dna["traits"]["tempo"]["median"] == 80


def _catalog_from(bp, extra_bars=0):
    """A fake catalog song whose chords per bar copy the blueprint's."""
    return [{"song_id": "a" * 12, "title": "Old Song", "roman_per_bar": blueprint_bars(bp) + ["I"] * extra_bars},
            {"song_id": "b" * 12, "title": "Other Song", "roman_per_bar": ["ii", "V", "I", "vi"] * 10}]


def test_gate_harmony_copy_is_flagged_original_passes():
    bp = build_blueprint("", voice_range=VOICE, era="90s_rnb", key="C major", tempo=90)
    flagged = harmony_check(bp, _catalog_from(bp))
    assert flagged["status"] == "flag" and flagged["hits"][0]["title"] == "Old Song"
    assert flagged["hits"][0]["bars"] >= 16
    unrelated = harmony_check(bp, [{"song_id": "c" * 12, "title": "Different",
                                    "roman_per_bar": ["♭VII", "♭III", "♭VI", "v"] * 20}])
    assert unrelated["status"] == "pass"
    # the blueprint's own originality checks include the catalog harmony comparison
    edited = revise(bp, {}, catalog=[dict(c, bpm=60, key="E major", form="") for c in _catalog_from(bp)])
    assert any(c["id"] == "catalog_harmony" and c["status"] == "flag" for c in edited["originality"]["checks"])


def test_gate_melody_copy_is_flagged_original_passes():
    bp = build_blueprint("", "[Verse]\nsing a line of words here now\n[Chorus]\nhold on to me tonight babe",
                         voice_range=VOICE, era="90s_rnb", key="A♭ major", tempo=88)
    melody = arrange(bp, seed=2)["tracks"]["melody"]
    ours = [n[2] for n in sorted(melody)]
    # an old song whose vocal contains 40 notes of ours, transposed, inside other material
    rng = np.random.default_rng(1)
    filler = list(rng.integers(55, 70, 60))
    copied = [{"song_id": "a" * 12, "title": "Old Song", "midis": filler[:30] + [p - 3 for p in ours[:40]] + filler[30:]}]
    res = melody_check(melody, copied)                                        # transposed copy still caught
    assert res["status"] == "flag" and res["hits"][0]["intervals"] >= 8
    different = [{"song_id": "b" * 12, "title": "Other", "midis": [60, 67, 55, 72, 50, 64, 59, 70, 52, 66] * 3}]
    assert melody_check(melody, different)["status"] == "pass"
    assert melody_check(melody, [])["songs_compared"] == 0


def test_step_only_runs_at_chance_level_are_not_flagged():
    """AU-12 finding on real data: shuffled melodies share step runs of 6-11 by chance."""
    rng = np.random.default_rng(3)
    ours = [(i * 0.5, 0.5, int(p), 90) for i, p in enumerate(60 + np.cumsum(rng.choice([-2, -1, 0, 1, 2], 200)))]
    theirs = [{"song_id": "a" * 12, "title": "Steps", "midis": list(60 + np.cumsum(rng.choice([-2, -1, 0, 1, 2], 300)))}]
    assert melody_check(ours, theirs)["status"] != "flag"


def test_repeated_note_runs_do_not_count_as_copies():
    melody = [(i * 0.5, 0.5, 60, 90) for i in range(20)]                     # one note repeated
    same = [{"song_id": "a" * 12, "title": "Drone", "midis": [64] * 20}]
    assert melody_check(melody, same)["status"] == "pass"
