from types import SimpleNamespace

import pytest

from auralis.artist.dna import _families, build_dna, canonical_loop, family_key


def song(sid, title, kind="stem-set", variants=(), included=True):
    return SimpleNamespace(id=sid, title=title, kind=kind, variants=list(variants),
                           included=included, analysis_status="done")


def analysis(bpm=90.0, tonic=0, mode="minor", loops=(("i", "i", "♭VI", "i"),), melody=True,
             form="Intro V C V C Outro", drums=True):
    roles = form.split()
    names = {"Intro": "intro", "V": "verse", "C": "chorus", "PC": "pre-chorus", "B": "bridge", "Outro": "outro"}
    sections, t = [], 0.0
    for i, r in enumerate(roles):
        role = names[r]
        sections.append({"start_bar": i * 8, "bars": 8, "start_seconds": t, "end_seconds": t + 20,
                         "label": chr(65 + i), "energy": 0.9 if role == "chorus" else 0.5,
                         "arrangement": {}, "role_guess": role})
        t += 20
    return {
        "global": {"integrated_lufs": -14.0, "stereo_width": 0.25, "loudness_range_lu": 6.0,
                   "vocal_melody_found": melody},
        "tempo": {"bpm": bpm},
        "key": {"tonic": tonic, "mode": mode, "name": "x", "confidence": 0.4},
        "harmony": {"changes_per_bar": 1.0, "diatonic_share": 0.9,
                    "top_progressions": [{"progression": list(p), "count": 1} for p in loops],
                    "vocabulary": {"i": 0.6, "♭VI": 0.4}},
        "structure": {"sections": sections, "roles_form": form},
        "rhythm": {"source": "drums stem" if drums else "percussive mix", "syncopation": 0.5,
                   "onsets_per_beat": 1.5, "swing_position": 0.5},
        "melody": {"range_low_midi": 55.0, "range_high_midi": 70.0, "phrase_beats_median": 4.0,
                   "interval_profile": {"repeat": 0.2, "step": 0.5, "skip": 0.2, "leap": 0.1}} if melody else None,
        "production": {"low_ratio": 0.7, "vocal_to_music_db": -5.0},
    }


# ── Versions of one song ────────────────────────────────────────────────────

def test_family_key_strips_version_words():
    assert family_key("Night Signal (Instrumental)") == "night signal"
    assert family_key("[site.com] Slow Tide Deep House Remix (2)") == "slow tide"
    assert family_key("Gold Line Feat. Someone & Other") == "gold line"


def test_families_group_versions_but_not_shared_first_words():
    fam = _families({"a": "Velvet Hour", "b": "Velvet Hour trap rnb", "c": "Velvet Hour this the one",
                     "d": "Studio Atlanta Sketch 1", "e": "Studio Midnight Type Beat"})
    assert fam["a"] == fam["b"] == fam["c"]
    assert fam["d"] != fam["e"]            # one shared word is not the same song


def test_versions_share_one_songs_weight():
    songs = [song("a", "Song A"), song("b", "Song A (Instrumental)"), song("c", "Song A Remix"),
             song("d", "Song B")]
    analyses = {"a": analysis(bpm=80), "b": analysis(bpm=80), "c": analysis(bpm=80), "d": analysis(bpm=120)}
    dna = build_dna(songs, analyses)
    assert dna["method"]["song_families"] == 2
    # Three versions of Song A weigh the same as Song B, so the middle is between.
    assert 80 <= dna["traits"]["tempo"]["median"] <= 120
    assert dna["traits"]["tempo"]["bands"] == {"120s": 0.5, "80s": 0.5}


def test_switched_off_songs_are_ignored():
    songs = [song("a", "Mine", included=True), song("b", "Not mine", included=False)]
    analyses = {"a": analysis(bpm=90), "b": analysis(bpm=140)}
    dna = build_dna(songs, analyses)
    assert dna["method"]["songs_used"] == 1 and dna["method"]["songs_switched_off"] == 1
    assert dna["traits"]["tempo"]["median"] == pytest.approx(90)


def test_covers_count_less():
    songs = [song("a", "Own"), song("b", "Somebody Else Cover", variants=["cover"])]
    analyses = {"a": analysis(bpm=90), "b": analysis(bpm=130)}
    dna = build_dna(songs, analyses)
    assert dna["traits"]["tempo"]["bands"]["90s"] > dna["traits"]["tempo"]["bands"]["130s"]


# ── Traits ─────────────────────────────────────────────────────────────────

def test_relative_keys_share_a_family():
    songs = [song("a", "A"), song("b", "B")]
    analyses = {"a": analysis(tonic=9, mode="minor"),      # A minor
                "b": analysis(tonic=0, mode="major")}      # C major, same signature
    fam = build_dna(songs, analyses)["traits"]["key"]["families"]
    assert len(fam) == 1 and fam[0]["share"] == 1.0
    assert "C major / A minor" in fam[0]["signature"]


def test_loop_rotations_are_one_loop():
    assert canonical_loop(["v", "i", "v", "i"]) == canonical_loop(["i", "v", "i", "v"]) == "i – v – i – v"
    songs = [song("a", "A"), song("b", "B")]
    analyses = {"a": analysis(loops=[("v", "i", "v", "i")]), "b": analysis(loops=[("i", "v", "i", "v")])}
    loops = build_dna(songs, analyses)["traits"]["harmony"]["loops"]["minor"]
    assert loops[0]["progression"] == "i – v – i – v" and len(loops) == 1


def test_form_and_lift():
    songs = [song(str(i), f"Song {i}") for i in range(3)]
    analyses = {str(i): analysis(form="Intro V C V C B C Outro") for i in range(3)}
    form = build_dna(songs, analyses)["traits"]["form"]
    assert form["common_forms"][0]["form"] == "Intro V C V C B C Outro"
    assert form["first_chorus_seconds"] == pytest.approx(40)
    assert form["chorus_lift"] == pytest.approx(0.4)


def test_melody_only_from_songs_with_a_vocal_stem():
    songs = [song("a", "A"), song("b", "B")]
    analyses = {"a": analysis(melody=False), "b": analysis(melody=False)}
    assert "melody" not in build_dna(songs, analyses)["traits"]


def test_voice_fit_compares_writing_range_to_trained_range():
    voice = SimpleNamespace(id="v", name="Me", pitch_low_midi=50.0, pitch_high_midi=72.0)
    dna = build_dna([song("a", "A")], {"a": analysis()}, voice)
    v = dna["traits"]["voice"]
    assert v["headroom_semitones"] == pytest.approx(2.0)     # 72 - 70
    assert v["footroom_semitones"] == pytest.approx(5.0)     # 55 - 50


def test_every_trait_says_how_much_to_trust_it():
    songs = [song(str(i), f"Song {i}") for i in range(3)]
    dna = build_dna(songs, {str(i): analysis() for i in range(3)})
    for name, trait in dna["traits"].items():
        assert trait["summary"]
        assert trait["confidence"] in ("strong", "moderate", "weak"), name


def test_empty_when_nothing_is_switched_on():
    dna = build_dna([song("a", "A", included=False)], {"a": analysis()})
    assert dna.get("empty") is True and dna["traits"] == {}


def test_api_dna(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import artist, main
    from auralis.artist.library import LibraryStore

    monkeypatch.setattr(artist, "LIBRARY", LibraryStore(tmp_path / "artist"))
    response = TestClient(main.app).get("/artist/dna")
    assert response.status_code == 200 and response.json()["empty"] is True
