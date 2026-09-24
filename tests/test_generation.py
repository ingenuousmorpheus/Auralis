"""AU-05 structured composer: arrangement, MIDI, local synth render, mix/master, API."""
import time

import librosa
import numpy as np
import pytest
import soundfile as sf

from auralis.composer import build_blueprint, revise
from auralis.composer.arrange import CRASH, KICK, SCALES, arrange
from auralis.composer.chords import chord_tones, parse_key
from auralis.composer.midi import read_midi, write_midi
from auralis.projects.jobs import job_outputs

VOICE = (50.0, 72.0)


def _short(key="C major", tempo=110.0, era="90s_rnb"):
    """A 12-bar blueprint (intro 2, verse 4, chorus 4, outro 2) so renders stay quick."""
    bp = build_blueprint("", voice_range=VOICE, era=era, key=key, tempo=tempo)
    by_type = {}
    for s in bp["sections"]:
        by_type.setdefault(s["type"], s["id"])
    plan = [("intro", 2), ("verse", 4), ("chorus", 4), ("outro", 2)]
    bp = revise(bp, {"sections": [{"id": by_type[t], "bars": b} for t, b in plan]})
    assert bp["validation"]["ok"], bp["validation"]
    return bp


@pytest.mark.parametrize("token,key,pcs", [
    ("Imaj7", "C major", {0, 4, 7, 11}), ("ii9", "C major", {2, 5, 9, 0, 4}),
    ("V9sus", "C major", {7, 0, 2, 5, 9}), ("i9", "A minor", {9, 0, 4, 7, 11}),
    ("♭VImaj7", "A minor", {5, 9, 0, 4}), ("iv6", "C major", {5, 8, 0, 2}),
])
def test_chord_tones(token, key, pcs):
    tonic, mode = parse_key(key)
    root, tones, bass = chord_tones(token, tonic, mode)
    assert {(root + t) % 12 for t in tones} == pcs
    assert chord_tones("IV/V", 0, "major")[2] == 7


def test_arrangement_follows_the_blueprint():
    bp = build_blueprint("", voice_range=VOICE, era="neo_soul", key="E♭ major", tempo=90)
    a = arrange(bp, seed=1)
    tonic, mode = parse_key(bp["key"])
    assert a["counts"]["keys"] and a["counts"]["bass"] and a["counts"]["drums"] and a["counts"]["melody"]
    # every keys note is a tone of the chord sounding at that moment
    for s in bp["sections"]:
        start = (s["start_bar"] - 1) * 4
        for c in s["chords"]:
            c0 = start + (c["bar"] - 1) * 4 + (c["beat"] - 1)
            root, tones, _ = chord_tones(c["roman"], tonic, mode)
            want = {(root + t) % 12 for t in tones}
            notes = [n for n in a["tracks"]["keys"] if c0 <= n[0] < c0 + c["beats"] - 1e-6]
            assert all(n[2] % 12 in want for n in notes)
    # drums follow the arrangement: none in a section whose drums are off
    intro = bp["sections"][0]
    assert intro["arrangement"]["drums"] == "off"
    assert not [n for n in a["tracks"]["drums"] if n[0] < intro["bars"] * 4]
    # choruses arrive with a crash
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    assert any(n[2] == CRASH and n[0] == (chorus["start_bar"] - 1) * 4 for n in a["tracks"]["drums"])
    assert any(n[2] == KICK for n in a["tracks"]["drums"])


def test_voice_leading_moves_little():
    bp = build_blueprint("", voice_range=VOICE, era="neo_soul", key="C major", tempo=90)
    a = arrange(bp)
    onsets = {}
    for start, _, pitch, _ in a["tracks"]["keys"]:
        onsets.setdefault(start, []).append(pitch)
    chords = [sorted(v) for _, v in sorted(onsets.items())]
    moves = [sum(abs(x - y) for x, y in zip(p, q)) / len(p) for p, q in zip(chords, chords[1:]) if len(p) == len(q)]
    assert moves and np.median(moves) <= 3.0          # about a step per voice


def test_melody_guide_stays_in_the_vocal_register_and_scale():
    bp = build_blueprint("", "[Verse]\nthis is a line to sing\nanother line here\n[Chorus]\nsing it loud tonight",
                         voice_range=VOICE, era="90s_rnb", key="A♭ major", tempo=92)
    a = arrange(bp, seed=3)
    tonic, mode = parse_key(bp["key"])
    assert a["tracks"]["melody"]
    for s in bp["sections"]:
        v = s["vocal"]
        start, end = (s["start_bar"] - 1) * 4, (s["start_bar"] - 1 + s["bars"]) * 4
        notes = [n for n in a["tracks"]["melody"] if start <= n[0] < end]
        if not v:
            assert not notes
            continue
        for n in notes:
            assert v["low_midi"] <= n[2] <= v["high_midi"]
            assert (n[2] - tonic) % 12 in SCALES[mode]
    assert arrange(bp, seed=3)["tracks"] == a["tracks"]                      # deterministic
    assert arrange(bp, seed=4)["tracks"]["melody"] != a["tracks"]["melody"]  # the seed varies it


def test_midi_round_trip(tmp_path):
    bp = _short()
    a = arrange(bp)
    path = tmp_path / "a.mid"
    counts = write_midi(a, str(path))
    m = read_midi(str(path))
    assert m["format"] == 1 and m["tempo"] == pytest.approx(110, abs=0.01)
    names = {t["name"] for t in m["tracks"]}
    assert {"Keys (electric piano)", "Bass", "Drums"} <= names
    by_name = {t["name"]: t for t in m["tracks"]}
    assert len(by_name["Bass"]["notes"]) == counts["bass"] == len(a["tracks"]["bass"])
    first = a["tracks"]["bass"][0]
    got = by_name["Bass"]["notes"][0]
    assert got[0] == pytest.approx(first[0], abs=1 / 480) and got[2] == first[2]


def test_gate_render_complete_instrumental_ground_truth(tmp_path):
    """Render → analyse the audio → it matches the blueprint's tempo, key and chords."""
    from auralis.generation import render_instrumental
    from auralis.voice.pitch import detect_key

    bp = _short(key="D major", tempo=110)
    out = render_instrumental(bp, str(tmp_path / "r"), seed=0)
    assert set(out["stems"]) >= {"drums", "bass", "keys"}
    master, sr = sf.read(out["master_path"])
    assert master.ndim == 2 and sr == 44100
    assert abs(len(master) / sr - bp["duration_seconds"]) < 4
    assert np.sqrt((master ** 2).mean()) > 0.01
    assert out["after_peak_db"] <= -0.9
    drums = sf.read(out["stems"]["drums"])[0].mean(1).astype(np.float32)
    tempo, _ = librosa.beat.beat_track(y=drums[int(2 * 4 * 60 / 110 * sr):], sr=sr, start_bpm=110)
    assert abs(float(np.atleast_1d(tempo)[0]) - 110) <= 3
    harm = (sf.read(out["stems"]["keys"])[0].mean(1) + sf.read(out["stems"]["bass"])[0].mean(1)).astype(np.float32)
    key = detect_key(harm, sr)
    tonic, mode = parse_key(bp["key"])
    assert (key.tonic, key.mode) in ((tonic, mode), ((tonic + 9) % 12, "minor"))   # the key or its relative
    # the melody guide is rendered separately and never mixed into the instrumental
    assert out["melody_guide_path"] and "melody" not in out["stems"]


def test_render_job_maps_to_project_assets(tmp_path):
    from auralis.generation import render_instrumental

    bp = _short()
    out = render_instrumental(bp, str(tmp_path / "r"), master=False)
    job = {"kind": "instrumental-render", "stage": "done", "result": out}
    kinds = {(o.kind, o.name) for o in job_outputs(job)}
    assert ("generated", "arrangement.mid") in kinds and ("stem", "drums.wav") in kinds
    assert ("generated", "melody_guide.wav") in kinds


def test_api_render_download_and_save(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main, projects
    from auralis.projects import ProjectStore

    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    client = TestClient(main.app)
    assert client.get("/composer/providers").json()[0]["id"] == "synth"
    bp = _short()
    bad = dict(bp, tempo=999)
    assert client.post("/composer/render", json={"blueprint": bad}).status_code == 422
    job_id = client.post("/composer/render", json={"blueprint": bp, "master": False}).json()["job_id"]
    for _ in range(240):
        status = client.get(f"/jobs/{job_id}").json()
        if status["stage"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert status["stage"] == "done", status
    assert client.get(f"/composer/render/{job_id}/file/drums").status_code == 200
    midi = client.get(f"/composer/render/{job_id}/file/midi")
    assert midi.status_code == 200 and midi.content[:4] == b"MThd"
    assert client.get(f"/composer/render/{job_id}/file/nothing").status_code == 404
    pid = client.post("/projects", json={"name": "Render Test"}).json()["id"]
    saved = client.post(f"/projects/{pid}/import-job", json={"job_id": job_id})
    assert saved.status_code == 200, saved.text
