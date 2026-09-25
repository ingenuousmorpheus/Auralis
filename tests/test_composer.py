"""AU-04 Song Blueprint: brief reading, chord realisation, blueprint build, edits, saving."""
import json

import pytest

from auralis.composer import build_blueprint, parse_brief, regenerate, revise, validate_blueprint
from auralis.composer.chords import ChordError, key_name, parse_key, realise, split_progression
from auralis.projects import ProjectStore
from auralis.theory import load_atlas
from auralis.theory.schema import FORBIDDEN_KEYS

VOICE = (50.0, 72.0)          # D3–C5


def _dna(minor_share=0.7, median=92.0):
    """A small synthetic Artist DNA with the fields the composer reads."""
    return {
        "method": {"songs_used": 12},
        "traits": {
            "tempo": {"median": median, "low": 84.0, "high": 100.0},
            "key": {"minor_share": minor_share,
                    "families": [{"major_tonic": 1, "share": 0.3}, {"major_tonic": 8, "share": 0.2}]},
            "harmony": {"changes_per_bar": 1.2,
                        "loops": {"minor": [{"progression": "i – i – i – ♭VI", "weight": 3.0},
                                            {"progression": "i – v – i – v", "weight": 2.0}],
                                  "major": [{"progression": "I – vi – iii – vi", "weight": 2.0}]}},
            "form": {"common_forms": [{"form": "Intro V PC C V PC C B C Outro", "weight": 2.0},
                                      {"form": "V C V C", "weight": 1.0}],
                     "first_chorus_seconds": 40.0, "intro_bars": 8.0,
                     "section_bars": {"chorus": 8.0, "pre-chorus": 4.0}, "chorus_lift": 0.3},
            "groove": {"syncopation": 0.5},
            "melody": {"range_low_midi": 54.0, "range_high_midi": 70.0, "phrase_beats": 3.0},
            "production": {"low_ratio": 0.7, "stereo_width": 0.25},
        },
    }


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


# ── Brief ──────────────────────────────────────────────────────────────────

def test_brief_reads_clear_words_and_records_them():
    b = parse_brief("Dark late-night neo soul, 88 BPM, big chorus, falsetto, no bridge, about 3:10")
    assert b["era"] == "neo_soul" and b["tempo"] == 88 and b["mode"] == "minor"
    assert b["chorus_emphasis"] and b["bridge"] is False and b["length_seconds"] == 190
    assert b["vocal"] == "falsetto"
    assert {h["field"] for h in b["heard"]} >= {"era", "tempo", "mode", "bridge", "length_seconds"}


def test_brief_key_and_explicit_settings_win():
    b = parse_brief("happy song in F# minor", era="90s_rnb", key="E♭ major")
    assert (b["key"]["tonic"], b["key"]["mode"]) == (3, "major")
    assert b["era"] == "90s_rnb" and set(b["set_by_you"]) == {"era", "key"}


def test_lyrics_headers_become_sections():
    b = parse_brief("", "[Verse 1]\nline one\nline two\n\n[Chorus]\nhook line\n(Bridge)\nturn\n")
    assert [blk["type"] for blk in b["lyric_sections"]] == ["verse", "chorus", "bridge"]
    assert b["lyric_sections"][0]["lines"] == ["line one", "line two"]


# ── Chords ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token,key,expected", [
    ("ii9", "A♭ major", "B♭m9"), ("IV/V", "A♭ major", "D♭/E♭"), ("Imaj7", "C major", "Cmaj7"),
    ("♭VImaj7", "F♯ minor", "Dmaj7"), ("♭VII", "A minor", "G"), ("V9sus", "C major", "G9sus4"),
    ("IVmaj7/1", "D major", "Gmaj7/D"), ("iv6", "C major", "Fm6"), ("V13", "E major", "B13"),
    ("i9", "B♭ minor", "B♭m9"), ("VI7", "C major", "A7"),
])
def test_roman_numerals_realise_in_any_key(token, key, expected):
    tonic, mode = parse_key(key)
    assert realise(token, tonic, mode) == expected


def test_keys_parse_and_bad_tokens_fail():
    assert parse_key("C#m") == (1, "minor") and parse_key("Bb") == (10, "major")
    assert key_name(1, "major") == "D♭ major" and key_name(8, "minor") == "G♯ minor"
    assert split_progression("ii9 – V13 – Imaj9") == ["ii9", "V13", "Imaj9"]
    with pytest.raises(ChordError):
        realise("Cmaj7", 0, "major")


# ── Blueprint ──────────────────────────────────────────────────────────────

def test_gate_blueprint_is_complete_and_explained():
    bp = build_blueprint("Dark late-night R&B, big chorus", dna=_dna(), voice_range=VOICE, voice_name="Test Voice")
    assert bp["validation"]["ok"], bp["validation"]
    assert 40 <= bp["tempo"] <= 220 and bp["meter"] == "4/4" and bp["mode"] == "minor"
    types = [s["type"] for s in bp["sections"]]
    assert types[0] == "intro" and types[-1] == "outro" and types.count("chorus") >= 2
    for s in bp["sections"]:
        assert s["bars"] > 0 and s["chords"] and s["why"]
        assert sum(c["beats"] for c in s["chords"]) == s["bars"] * 4
        assert all(c["chord"] != "?" for c in s["chords"])
        assert set(s["arrangement"]) == {"drums", "bass", "keys", "pad", "lead_vocal", "backing_vocals", "fx", "atmos"}
    assert len(bp["energy_curve"]) == bp["total_bars"]
    for field in ("era", "mode", "tempo", "key", "form", "energy", "groove", "arrangement"):
        assert bp["why"][field], field
    # vocal-range constraints stay inside the voice, a semitone under the top
    for s in bp["sections"]:
        if s["vocal"]:
            assert VOICE[0] <= s["vocal"]["low_midi"] <= s["vocal"]["peak_midi"] <= VOICE[1] - 1
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    verse = next(s for s in bp["sections"] if s["type"] == "verse")
    assert chorus["energy"] > verse["energy"] and chorus["vocal"]["peak_midi"] > verse["vocal"]["peak_midi"]
    assert chorus["arrangement"]["backing_vocals"] == "full"


def test_blueprint_never_carries_melody_or_transcription():
    bp = build_blueprint("smooth 90s ballad", dna=_dna(), voice_range=VOICE)
    bad = {k for k in _walk_keys({k: v for k, v in bp.items() if k != "lyrics"})
           if k.lower() in FORBIDDEN_KEYS and k != "lyrics"}
    assert not bad
    assert any(c["id"] == "no_copied_material" and c["status"] == "pass" for c in bp["originality"]["checks"])


def test_catalog_loops_are_revoiced_and_used_once_and_chorus_differs():
    bp = build_blueprint("dark", dna=_dna(), voice_range=VOICE, era="modern_alt_rnb", artist_dna_weight=0.9)
    dna_types = {s["type"] for s in bp["sections"] if s["progression"]["source"] == "dna"}
    assert len(dna_types) == 1
    s = next(s for s in bp["sections"] if s["progression"]["source"] == "dna")
    assert s["progression"]["roman"] != split_progression(s["progression"]["dna_loop"])   # re-voiced
    prog = {s["type"]: s["progression"]["roman"] for s in bp["sections"]}
    assert prog["verse"] != prog["chorus"]


def test_key_is_chosen_for_the_voice_and_prefers_dna_families():
    bp = build_blueprint("", dna=_dna(minor_share=0.2), voice_range=VOICE, era="80s_quiet_storm")
    assert bp["mode"] == "major"
    assert "fit your range" in bp["why"]["key"][0] or "stretches" in bp["why"]["key"][0]
    narrow = build_blueprint("", voice_range=(57.0, 64.0), era="80s_quiet_storm")
    assert "stretches your range" in narrow["why"]["key"][0]


def test_era_without_the_dna_mode_follows_the_era():
    bp = build_blueprint("", dna=_dna(minor_share=0.9), voice_range=VOICE, era="80s_quiet_storm")
    assert bp["mode"] == "major" and "every" in bp["why"]["mode"][0]


def test_tempo_follows_dna_inside_the_era_band_or_the_prompt():
    assert build_blueprint("", dna=_dna(median=92), voice_range=VOICE, era="90s_rnb")["tempo"] == 92
    halved = build_blueprint("", dna=_dna(median=150), voice_range=VOICE, era="80s_quiet_storm")
    assert halved["tempo"] == 75 and "half-time" in halved["why"]["tempo"][0]
    assert build_blueprint("slow jam 70 bpm", voice_range=VOICE)["tempo"] == 70


def test_form_follows_lyrics_and_prompt_length():
    bp = build_blueprint("", "[Verse]\na\nb\n[Chorus]\nc\n[Verse]\nd\n[Chorus]\ne", voice_range=VOICE)
    assert [s["type"] for s in bp["sections"]] == ["intro", "verse", "chorus", "verse", "chorus", "outro"]
    assert bp["sections"][1]["lyrics"] == ["a", "b"]
    short = build_blueprint("short song, no bridge", dna=_dna(), voice_range=VOICE)
    assert "bridge" not in [s["type"] for s in short["sections"]]
    assert short["duration_seconds"] < 200


def test_works_without_dna_or_voice():
    bp = build_blueprint("")
    assert bp["validation"]["ok"] and bp["vocal"]["range_source"].startswith("a default")


def test_catalog_twin_is_flagged():
    bp = build_blueprint("", voice_range=VOICE, era="90s_rnb", key="A minor", tempo=90)
    form = " ".join({"intro": "Intro", "verse": "V", "pre-chorus": "PC", "chorus": "C", "bridge": "B",
                     "outro": "Outro"}[s["type"]] for s in bp["sections"])
    flagged = revise(bp, {}, catalog=[{"bpm": 91.0, "key": "A minor", "form": form}])
    assert any(c["id"] == "catalog_twin" and c["status"] == "flag" for c in flagged["originality"]["checks"])
    clear = revise(bp, {}, catalog=[{"bpm": 120.0, "key": "A minor", "form": form}])
    assert all(c["status"] != "flag" for c in clear["originality"]["checks"])


# ── Editing ────────────────────────────────────────────────────────────────

def test_edit_key_and_tempo_rederives_chords_timings_and_registers():
    bp = build_blueprint("", voice_range=VOICE, era="90s_rnb", key="A♭ major", tempo=90)
    ed = revise(bp, {"key": "E major", "tempo": 60})
    assert ed["revision"] == bp["revision"] + 1 and {"key", "tempo"} <= set(ed["edited"])
    first = ed["sections"][1]
    assert first["chords"][0]["chord"] == realise(first["progression"]["roman"][0], 4, "major")
    assert ed["duration_seconds"] == pytest.approx(bp["duration_seconds"] * 1.5, rel=0.01)
    assert ed["why"]["key"][0].startswith("You set")


def test_edit_sections_bars_chords_and_order():
    bp = build_blueprint("", voice_range=VOICE, era="neo_soul", key="C major")
    secs = [{"id": s["id"]} for s in bp["sections"]]
    secs[1] = {"id": bp["sections"][1]["id"], "bars": 4, "progression": "ii7 V7 Imaj7", "energy": 0.4}
    secs.insert(2, {"type": "bridge"})                       # a new section
    secs = secs[:-1]                                          # drop the outro
    ed = revise(bp, {"sections": secs})
    assert ed["validation"]["ok"], ed["validation"]
    v = ed["sections"][1]
    assert v["bars"] == 4 and [c["chord"] for c in v["chords"]] == ["Dm7", "G7", "Cmaj7", "Dm7"]
    assert v["progression"]["source"] == "edited" and v["why"][0] == "You edited these chords."
    assert ed["sections"][2]["type"] == "bridge" and ed["sections"][2]["chords"]
    assert ed["sections"][-1]["type"] != "outro"
    assert ed["total_bars"] == sum(s["bars"] for s in ed["sections"])


def test_invalid_edits_are_reported():
    bp = build_blueprint("", voice_range=VOICE)
    bad = revise(bp, {"tempo": 400, "sections": [{"id": bp["sections"][0]["id"], "progression": "Cmaj7 Fmaj7"}]})
    errors = " ".join(bad["validation"]["errors"])
    assert "Tempo" in errors and "not Roman numerals" in errors


def test_regenerate_changes_one_section_type_only():
    bp = build_blueprint("", dna=_dna(minor_share=0.1), voice_range=VOICE, era="90s_rnb")
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    new = regenerate(bp, chorus["id"])
    before = {s["id"]: s["progression"]["roman"] for s in bp["sections"]}
    after = {s["id"]: s["progression"]["roman"] for s in new["sections"]}
    changed = {sid for sid in before if before[sid] != after[sid]}
    assert changed and {s["type"] for s in new["sections"] if s["id"] in changed} == {"chorus"}
    assert len({tuple(after[s["id"]]) for s in new["sections"] if s["type"] == "chorus"}) == 1


# ── Saving ─────────────────────────────────────────────────────────────────

def test_blueprint_saves_into_a_project_with_revisions(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create("Blueprint Test")
    bp = build_blueprint("", "[Verse]\nfirst line", voice_range=VOICE)
    store.save_blueprint(project.id, bp)
    store.save_blueprint(project.id, revise(bp, {"tempo": 80}))
    assert store.blueprint(project.id)["tempo"] == 80
    assert [r["saved_revision"] for r in store.blueprint_revisions(project.id)] == [1, 2]
    assert (tmp_path / project.id / "lyrics.txt").read_text("utf-8").strip() == "[Verse]\nfirst line"
    reopened = ProjectStore(tmp_path)                          # survives a new store (restart)
    assert reopened.blueprint(project.id)["saved_revision"] == 2
    store.close(project.id)
    with pytest.raises(PermissionError):
        store.save_blueprint(project.id, bp)


def test_api_create_revise_regenerate_save(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import artist, main, projects
    from auralis.artist.library import LibraryStore

    monkeypatch.setattr(artist, "LIBRARY", LibraryStore(tmp_path / "artist"))
    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    client = TestClient(main.app)
    r = client.post("/composer/blueprint", json={"prompt": "romantic 80s quiet storm", "use_voice": False})
    assert r.status_code == 200
    bp = r.json()
    assert bp["era"]["id"] == "80s_quiet_storm" and bp["validation"]["ok"]
    r = client.post("/composer/blueprint/revise", json={"blueprint": bp, "changes": {"tempo": 70}})
    assert r.status_code == 200 and r.json()["tempo"] == 70
    bad = client.post("/composer/blueprint/revise", json={"blueprint": bp, "changes": {"key": "H major"}})
    assert bad.status_code == 422
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    assert client.post("/composer/blueprint/regenerate",
                       json={"blueprint": bp, "section_id": chorus["id"]}).status_code == 200
    pid = client.post("/projects", json={"name": "API Blueprint"}).json()["id"]
    assert client.put(f"/projects/{pid}/blueprint", json={"blueprint": bp}).status_code == 200
    assert client.get(f"/projects/{pid}/blueprint").json()["id"] == bp["id"]
    assert len(client.get(f"/projects/{pid}/blueprint/revisions").json()) == 1
