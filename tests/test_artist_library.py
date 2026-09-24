import json
import os
import tempfile
import time
import zipfile

import numpy as np
import pytest
import soundfile as sf

from auralis.artist.analyze import analyse_song
from auralis.artist.library import (LibraryStore, SongAudio, clean_title, looks_like_stem,
                                    scan_source, stem_role, variants)

SR = 22050
BPM = 90.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
PROGRESSION = [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")]   # C G Am F


def _tone(freq, seconds, amp=0.2):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def synthetic_song(form=("V", "C", "V", "C"), bars_per_section=8):
    """Stems for a song whose tempo, key, chords and form are known."""
    rng = np.random.default_rng(0)
    total = int(SR * BAR * bars_per_section * len(form))
    stems = {r: np.zeros(total, np.float32)
             for r in ("lead_vocal", "backing_vocal", "drums", "bass", "harmonic")}
    t_bar = np.arange(int(SR * BAR)) / SR
    env = np.minimum(1, np.minimum(t_bar / 0.02, (BAR - t_bar) / 0.05)).astype(np.float32)
    bar_index = 0
    for section in form:
        chorus = section == "C"
        for b in range(bars_per_section):
            start = int(bar_index * BAR * SR)
            root, quality = PROGRESSION[b % 4]
            third = 3 if quality == "min" else 4
            chord = sum(_tone(_hz(60 + root + i), BAR, 0.08) for i in (0, third, 7))
            seg = slice(start, start + len(t_bar))
            stems["harmonic"][seg] += chord * env * (2.0 if chorus else 1.0)
            stems["bass"][seg] += _tone(_hz(36 + root), BAR, 0.25) * env
            for beat in range(4):
                s = start + int(beat * BEAT * SR)
                if beat in (0, 2):
                    n = int(0.15 * SR)
                    kick = _tone(55, 0.15, 0.9) * np.exp(-np.arange(n) / (0.04 * SR))
                    stems["drums"][s:s + n] += kick.astype(np.float32)
                else:
                    n = int(0.12 * SR)
                    stems["drums"][s:s + n] += (rng.standard_normal(n) * 0.4 *
                                                np.exp(-np.arange(n) / (0.03 * SR))).astype(np.float32)
                note = 64 + root % 5 + (7 if chorus else 0)
                n = int(BEAT * 0.9 * SR)
                stems["lead_vocal"][s:s + n] += _tone(_hz(note), BEAT * 0.9, 0.2)
                if chorus:
                    stems["backing_vocal"][s:s + n] += _tone(_hz(note + 4), BEAT * 0.9, 0.12)
            bar_index += 1
    mix = sum(stems.values())
    return np.stack([mix, mix], axis=1), stems


# ── Naming and grouping ────────────────────────────────────────────────────

@pytest.mark.parametrize("name,role", [
    ("0 Lead Vocals.wav", "lead_vocal"), ("1 Backing Vocals.wav", "backing_vocal"),
    ("song_drums_KITS_Oct 28, 2024.wav", "drums"), ("bass.wav", "bass"),
    ("5 Keyboard.wav", "harmonic"), ("Night Drive (Remix) (FX).mp3", "other"),
    ("My Song Final.wav", None),
])
def test_stem_roles(name, role):
    assert stem_role(name) == role


def test_kits_backing_is_an_instrumental_not_a_stem():
    assert not looks_like_stem("Song A_backing_KITS_Jan_30__2025.wav")
    assert not looks_like_stem("Song_B vocal guide.mp3")
    assert looks_like_stem("song b_vocals_KITS_Oct 28, 2024.wav")


def test_titles_and_variants():
    assert clean_title("Song C Master Final edm 2.wav.wav") == "Song C Master Final edm 2"
    assert clean_title("02 Song D.wav") == "Song D"
    assert variants("Song E (Instrumental)") == ["instrumental"]
    assert "cover" in variants("Song F Trap Cover")


def _write(path, seconds=2.0, freq=220.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.stack([_tone(freq, seconds)] * 2, 1), SR)


def _catalog(root):
    _write(root / "01 Song One.wav")
    _write(root / "02 Song One (Instrumental).wav")
    stems = root / "Song Two"
    for name in ("bass.wav", "drums.wav", "song two_vocals_KITS_x.wav", "Song Two DEMO.wav"):
        _write(stems / name)
    (stems / "song two lyrics.txt").write_text("words", encoding="utf-8")
    versions = root / "Song Three"
    _write(versions / "song three.wav")
    _write(versions / "song three_drums_KITS_x.wav")
    with zipfile.ZipFile(root / "Song Four Stems.zip", "w") as archive:
        for name in ("0 Lead Vocals.wav", "1 Drums.wav", "2 Bass.wav"):
            tmp = root / f"_{name}"
            _write(tmp)
            archive.write(tmp, name)
            tmp.unlink()


def test_scan_groups_loose_files_stem_folders_and_zips(tmp_path):
    root = tmp_path / "catalog"
    _catalog(root)
    skipped = []
    songs = {s.title: s for s in scan_source(root, "src", skipped)}
    assert set(songs) == {"Song One", "Song One (Instrumental)", "Song Two",
                          "song three", "Song Four"}
    assert songs["Song Two"].kind == "stem-set"
    roles = sorted(f.role for f in songs["Song Two"].files)
    assert roles == ["bass", "drums", "reference", "vocal"]
    assert songs["Song Two"].lyrics_path.endswith("song two lyrics.txt")
    assert songs["Song Four"].kind == "stem-set"
    assert sorted(f.role for f in songs["Song Four"].files) == ["bass", "drums", "lead_vocal"]
    assert songs["Song One (Instrumental)"].variants == ["instrumental"]
    assert [os.path.basename(p) for p in skipped] == ["song three_drums_KITS_x.wav"]


def test_zip_stems_load_and_leave_no_temp_files(tmp_path):
    root = tmp_path / "catalog"
    _catalog(root)
    song = next(s for s in scan_source(root, "src") if s.title == "Song Four")
    before = {p for p in os.listdir(tempfile.gettempdir()) if p.startswith("auralis_catalog_")}
    mix, sr, stems = SongAudio(song).load()
    after = {p for p in os.listdir(tempfile.gettempdir()) if p.startswith("auralis_catalog_")}
    assert sr == SR and mix.shape[1] == 2
    assert sorted(stems) == ["bass", "drums", "lead_vocal"]
    assert after == before


# ── Store ──────────────────────────────────────────────────────────────────

def _snapshot(root):
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*")}


def test_store_rescan_keeps_analysis_and_marks_changed_songs_stale(tmp_path, monkeypatch):
    root = tmp_path / "catalog"
    _write(root / "Song.wav", seconds=10)
    store = LibraryStore(tmp_path / "artist")
    store.add_source(str(root))
    assert store.rescan()["songs"] == 1
    song = store.songs()[0]
    store.update_song(song.id, analysis_status="done", included=False)
    store.rescan()
    assert store.song(song.id).analysis_status == "done"
    assert store.song(song.id).included is False
    _write(root / "Song.wav", seconds=12)                      # file changed
    store.rescan()
    assert store.song(song.id).analysis_status == "stale"


def test_analysis_never_writes_to_the_catalog(tmp_path):
    root = tmp_path / "catalog"
    mix, stems = synthetic_song(bars_per_section=4)
    root.mkdir()
    for role, audio in stems.items():
        sf.write(root / f"{role.replace('_', ' ')}.wav", audio, SR)
    store = LibraryStore(tmp_path / "artist")
    store.add_source(str(root))
    store.rescan()
    before = _snapshot(root)
    song = store.songs()[0]
    result = store.analyse(song.id)
    assert _snapshot(root) == before
    saved = json.loads((tmp_path / "artist" / "analyses" / f"{song.id}.json").read_text("utf-8"))
    assert saved["tempo"]["bpm"] == result["tempo"]["bpm"]
    assert store.song(song.id).analysis_status == "done"
    assert store.song(song.id).summary["key"]


def test_remove_source_forgets_songs_and_analyses(tmp_path):
    root = tmp_path / "catalog"
    _write(root / "Song.wav", seconds=10)
    store = LibraryStore(tmp_path / "artist")
    source = store.add_source(str(root))
    store.rescan()
    song_id = store.songs()[0].id
    (tmp_path / "artist" / "analyses" / f"{song_id}.json").write_text("{}")
    store.remove_source(source.id)
    assert store.songs() == []
    assert not (tmp_path / "artist" / "analyses" / f"{song_id}.json").exists()
    assert (root / "Song.wav").exists()


# ── Analysis against ground truth ──────────────────────────────────────────

@pytest.fixture(scope="module")
def analysed():
    mix, stems = synthetic_song()
    return analyse_song(mix, SR, stems)


def test_tempo_and_bars(analysed):
    assert abs(analysed["tempo"]["bpm"] - BPM) < 1.0      # regression, not the ~3 BPM grid
    assert 28 <= analysed["tempo"]["bar_count"] <= 33


def test_key_is_c_major(analysed):
    assert analysed["key"]["name"] == "C major"


def test_chords_follow_the_progression(analysed):
    romans = analysed["harmony"]["roman_per_bar"]
    expected = ["I", "V", "vi", "IV"]
    top = analysed["harmony"]["top_progressions"][0]["progression"]
    assert sorted(top) == sorted(expected)
    hits = sum(1 for i, r in enumerate(romans[:32]) if r in expected)
    assert hits / min(len(romans), 32) > 0.8


def test_structure_finds_the_repeating_chorus(analysed):
    sections = analysed["structure"]["sections"]
    choruses = [s for s in sections if s["role_guess"] == "chorus"]
    assert len(choruses) >= 2
    labels = {s["label"] for s in choruses}
    assert len(labels) == 1
    verse_like = [s for s in sections if s["role_guess"] != "chorus"]
    assert all(s["arrangement"]["backing_vocal"] < c["arrangement"]["backing_vocal"]
               for s in verse_like for c in choruses)


def test_mix_only_structure_finds_repeats_without_stems():
    mix, _ = synthetic_song()
    result = analyse_song(mix, SR)
    structure = result["structure"]
    assert structure["method"] == "mix repetition"
    labels = [s["label"] for s in structure["sections"]]
    assert any(labels.count(label) >= 2 for label in set(labels))
    assert result["melody"] is None and result["rhythm"]["source"] == "percussive mix"
    assert result["global"]["vocal_melody_found"] is None


def test_silent_vocal_stem_is_ignored_not_described():
    """An empty 'Lead Vocals' export must not invent a melody or look 'active'."""
    mix, stems = synthetic_song(form=("V", "C"), bars_per_section=4)
    stems["lead_vocal"] = stems["lead_vocal"] * 1e-4          # -80 dB bleed
    stems.pop("backing_vocal")
    result = analyse_song(mix, SR, stems)
    assert result["stems_ignored"] == ["lead_vocal"]
    assert result["melody"] is None
    assert result["global"]["vocal_melody_found"] is False
    assert "lead_vocal" not in result["production"]["instrumentation"]


def test_melody_range_comes_from_the_lead_stem(analysed):
    melody = analysed["melody"]
    assert 62 <= melody["range_low_midi"] <= 66
    assert 72 <= melody["range_high_midi"] <= 77
    assert melody["phrase_count"] >= 1


def test_rhythm_uses_the_drum_stem(analysed):
    rhythm = analysed["rhythm"]
    assert rhythm["source"] == "drums stem"
    assert rhythm["on_beat_share"] > 0.8


def test_production_reports_instrumentation(analysed):
    production = analysed["production"]
    assert set(production["instrumentation"]) == {"lead_vocal", "backing_vocal", "drums", "bass", "harmonic"}
    assert production["vocal_to_music_db"] is not None


# ── API ────────────────────────────────────────────────────────────────────

def test_api_library_flow(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import artist, main

    monkeypatch.setattr(artist, "LIBRARY", LibraryStore(tmp_path / "artist"))
    client = TestClient(main.app)
    assert client.post("/artist/library/sources", json={"path": str(tmp_path / "nope")}).status_code == 404

    root = tmp_path / "catalog"
    mix, stems = synthetic_song(bars_per_section=4)
    root.mkdir()
    sf.write(root / "Demo Song.wav", mix, SR)
    added = client.post("/artist/library/sources", json={"path": str(root)}).json()
    assert added["scan"]["songs"] == 1
    song_id = client.get("/artist/library").json()["songs"][0]["id"]

    started = client.post("/artist/library/analyze", json={}).json()
    assert started["total"] == 1
    for _ in range(600):
        status = client.get(f"/jobs/{started['job_id']}").json()
        if status["stage"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert status["stage"] == "done", status
    assert status["result"]["failed"] == []

    song = client.get(f"/artist/library/songs/{song_id}").json()
    assert song["analysis_status"] == "done"
    assert song["analysis"]["tempo"]["bpm"] > 0
    assert client.patch(f"/artist/library/songs/{song_id}", json={"included": False}).json()["included"] is False
    assert client.post("/artist/library/analyze", json={}).json()["total"] == 0


# ── Player previews ────────────────────────────────────────────────────────

def test_preview_streams_mixes_and_caches_one_stem_mixdown(tmp_path):
    root = tmp_path / "catalog"
    _catalog(root)
    store = LibraryStore(tmp_path / "artist")
    source = store.add_source(str(root))
    store.rescan()
    songs = {s.title: s for s in store.songs()}

    mix = songs["Song One"]
    assert store.preview_path(mix.id) == root / "01 Song One.wav"      # served in place

    before = _snapshot(root)
    stems = songs["Song Four"]
    first = store.preview_path(stems.id)
    assert first.parent == tmp_path / "artist" / "previews"            # never in the catalog
    data, sr = sf.read(first, always_2d=True)
    assert sr == SR and data.shape[1] == 2 and np.max(np.abs(data)) <= 0.99
    mtime = first.stat().st_mtime_ns
    assert store.preview_path(stems.id) == first and first.stat().st_mtime_ns == mtime  # cached
    assert _snapshot(root) == before

    store.remove_source(source.id)
    assert not first.exists()


def test_api_preview_route(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import artist, main

    monkeypatch.setattr(artist, "LIBRARY", LibraryStore(tmp_path / "artist"))
    client = TestClient(main.app)
    root = tmp_path / "catalog"
    _catalog(root)
    client.post("/artist/library/sources", json={"path": str(root)})
    songs = {s["title"]: s["id"] for s in client.get("/artist/library").json()["songs"]}
    response = client.get(f"/artist/library/songs/{songs['Song Four']}/preview")
    assert response.status_code == 200 and response.headers["content-type"] == "audio/wav"
    assert client.get("/artist/library/songs/nope/preview").status_code == 404
