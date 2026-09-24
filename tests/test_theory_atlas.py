import copy
import json

import pytest

from auralis.theory import candidates, eras, load_atlas, suggest_keys, validate_atlas
from auralis.theory.schema import FORBIDDEN_KEYS, is_roman


@pytest.fixture
def atlas():
    return copy.deepcopy(load_atlas())


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


# ── Data integrity ─────────────────────────────────────────────────────────

def test_canonical_atlas_is_valid_and_covers_every_era(atlas):
    assert validate_atlas(atlas) == []
    assert {e["id"] for e in eras(atlas)} == {
        "70s_soul", "80s_quiet_storm", "90s_rnb", "neo_soul", "2000s_rnb", "modern_alt_rnb"}


def test_every_row_has_provenance_and_an_honest_status(atlas):
    for group in ("eras", "progression_families", "chord_vocabulary", "vocal_patterns", "grooves", "section_lift", "evidence"):
        for row in atlas[group]:
            assert row["sources"], (group, row)
            assert row["status"] in ("sourced", "hypothesis")
            if row["sources"] == ["auralis_editorial"]:
                assert row["status"] == "hypothesis", (group, row)


# ── Copyright boundary ─────────────────────────────────────────────────────

def test_guard_rejects_melodies_and_lyrics(atlas):
    atlas["vocal_patterns"][0]["melody"] = [60, 62, 64]
    atlas["evidence"][0]["lyrics"] = "any words"
    problems = "\n".join(validate_atlas(atlas))
    assert "melody" in problems and "lyrics" in problems


def test_guard_rejects_absolute_chords_and_transcription_length(atlas):
    atlas["progression_families"][0]["roman"] = ["Cmaj7", "Fmaj7"]
    atlas["progression_families"][1]["roman"] = ["I"] * 12
    problems = "\n".join(validate_atlas(atlas))
    assert "'Cmaj7' is not a Roman numeral" in problems
    assert "2 to 8 chords" in problems


def test_guard_rejects_note_sequences_in_vocal_anchors(atlas):
    atlas["vocal_patterns"][0]["peak_degree"] = ["1", "2", "3", "5", "6"]
    assert any("must be one anchor" in p for p in validate_atlas(atlas))


def test_sourced_rows_need_a_real_source(atlas):
    atlas["grooves"][0]["status"] = "sourced"          # it only cites the editorial placeholder
    assert any("needs a source other than" in p for p in validate_atlas(atlas))


@pytest.mark.parametrize("token,ok", [("Imaj9", True), ("IV/V", True), ("♭VImaj7", True), ("V9sus", True),
                                      ("iv6", True), ("IVmaj7/1", True), ("Cmaj7", False), ("F#m", False)])
def test_roman_numerals(token, ok):
    assert is_roman(token) is ok


# ── The AU-03B gate ────────────────────────────────────────────────────────

def test_80s_rnb_returns_several_documented_transposable_candidates():
    result = candidates("80s_quiet_storm", voice_range=(50.0, 71.6))
    assert len(result["harmony"]) >= 3 and result["vocal"] and result["groove"]
    for h in result["harmony"]:
        assert all(is_roman(t) for t in h["roman"])            # transposable
        assert h["sources"] and all(s["title"] for s in h["sources"])
        assert h["keys"], "a key must always be suggested"
    for group in ("vocal", "groove"):
        for row in result[group]:
            assert row["sources"]
    assert not FORBIDDEN_KEYS & set(_all_keys(result))       # no melody anywhere in the answer


def test_filters_steer_candidates():
    romantic = candidates("80s_quiet_storm", harmony="romantic")["harmony"]
    assert all("romantic" in json.dumps(h) or h["era_affinity"] >= 0.7 for h in romantic)
    laid_back = candidates("neo_soul", groove="laid_back")["groove"]
    assert laid_back[0]["feel"] == "laid_back"


def test_unknown_era():
    with pytest.raises(KeyError):
        candidates("baroque")


# ── Keys chosen for the voice ──────────────────────────────────────────────

def test_keys_fit_the_voice_and_prefer_the_artists_key_families():
    keys = suggest_keys("major", (50.0, 71.6), dna_key_families=[8])     # A♭ major family
    assert keys[0]["key"] == "A♭ major"
    assert "fit your range" in keys[0]["why"] and "key family you use" in keys[0]["why"]


def test_minor_keys_use_the_relative_major_family():
    keys = suggest_keys("minor", None, dna_key_families=[8])     # A♭ major ↔ F minor
    assert keys[0]["key"] == "F minor"


def test_a_narrow_voice_still_gets_an_honest_answer():
    keys = suggest_keys("major", (60.0, 70.0))
    assert len(keys) == 3 and all("stretches your range" in k["why"] for k in keys)


# ── API and export ─────────────────────────────────────────────────────────

def test_api(monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main

    client = TestClient(main.app)
    assert len(client.get("/theory/eras").json()) == 6
    ok = client.get("/theory/candidates", params={"era": "neo_soul", "use_voice": False, "use_dna": False})
    assert ok.status_code == 200 and len(ok.json()["harmony"]) == 3
    assert client.get("/theory/candidates", params={"era": "baroque", "use_voice": False, "use_dna": False}).status_code == 404


def test_cheat_sheet_export_matches_the_json(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("export_atlas", Path(__file__).parents[1] / "tools" / "export_atlas.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = mod.sheets(load_atlas())
    assert list(data) == ["Era Profiles", "Progression Families", "Chord Vocabulary", "Vocal Phrase Patterns",
                          "Groove - Pocket", "Song Evidence", "Sources"]
    assert len(data["Progression Families"][1]) == len(load_atlas()["progression_families"])
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    assert mod.main(["--csv"]) == 0
    assert len(list((tmp_path / "atlas_csv").glob("*.csv"))) == 7
