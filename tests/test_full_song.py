"""AU-07 guide singer + AU-08 full-song voice pipeline (with a stand-in voice engine)."""
import shutil
import time

import librosa
import numpy as np
import pytest
import soundfile as sf

from auralis.composer import build_blueprint, revise
from auralis.composer.arrange import arrange
from auralis.voice.guide import build_score, onset_of, phrases, syllabify, vowel_of
from auralis.voice.pitch import _track_pitch
from auralis.voice.singing_provider import SR, get_singer

VOICE = (50.0, 72.0)
LYRICS = ("[Verse]\nI keep on thinking about the night we had\nall the city lights were fading into blue\n"
          "[Chorus]\nstay with me tonight\ndon't let the morning come")


def _short(lyrics=LYRICS, key="A♭ major"):
    bp = build_blueprint("smooth 90s R&B", lyrics, voice_range=VOICE, era="90s_rnb", key=key, tempo=88)
    ids = {}
    for s in bp["sections"]:
        ids.setdefault(s["type"], s["id"])
    return revise(bp, {"sections": [{"id": ids[t], "bars": b} for t, b in
                                    [("intro", 2), ("verse", 4), ("chorus", 4), ("outro", 2)]]})


def test_syllables_vowels_and_onsets():
    assert syllabify("I love the way you move tonight") == ["i", "love", "the", "way", "you", "move", "to", "night"]
    assert vowel_of("night") == "i" and vowel_of("stay") == "e" and vowel_of("you") == "u" and vowel_of("come") == "o"
    assert onset_of("stay") == "hiss" and onset_of("tonight") == "stop" and onset_of("love") == "soft" and onset_of("i") == ""
    assert onset_of("you") == "soft"


def test_score_lines_syllables_up_with_the_melody():
    bp = _short()
    score = build_score(bp, arrange(bp)["tracks"]["melody"])
    verse = [n for n in score if n.start < (bp["sections"][2]["start_bar"] - 1) * 4 * 60 / 88]
    assert verse and verse[0].syllable == "i" and verse[1].syllable == "keep"
    assert all(n.vowel in ("a", "e", "i", "o", "u", "uh") for n in score)
    assert len(phrases(score)) >= 2 and score[-1].phrase_end
    no_words = build_score(_short(lyrics=""), arrange(_short(lyrics=""))["tracks"]["melody"])
    assert no_words and all(n.syllable == "" for n in no_words)


def test_gate_guide_is_correctly_pitched_and_timed():
    """AU-07 gate: the dry guide vocal sings the blueprint melody at the written pitch and time."""
    bp = _short()
    score = build_score(bp, arrange(bp)["tracks"]["melody"])
    y = get_singer("vocalise").sing(score, bp["duration_seconds"] + 2)
    assert y.ndim == 1 and y.dtype == np.float32
    sung = np.abs(y) > 1e-4
    assert -24 < 20 * np.log10(np.sqrt(np.mean(y[sung] ** 2))) < -16 and np.abs(y).max() < 10 ** (-2.9 / 20)
    times, f0, prob = _track_pitch(y, SR)
    det = librosa.hz_to_midi(f0)
    ok = tot = 0
    for n in score:
        m = (times >= n.start + 0.06) & (times <= n.start + n.duration - 0.03)
        vals = det[m][np.isfinite(det[m])]
        if len(vals) < 3:
            continue
        tot += 1
        ok += abs(np.median(vals) - n.midi) <= 0.5
    assert tot >= 20 and ok / tot >= 0.9
    voiced = np.isfinite(det) & (prob > 0.45)
    errs = []
    for s, e in phrases(score):
        idx = np.where(voiced & (times >= s - 0.2) & (times <= s + 0.3))[0]
        if len(idx):
            errs.append(abs(times[idx[0]] - s))
    assert errs and np.median(errs) < 0.06


def test_chunks_short_whole_long_cut_in_rests():
    from auralis.voice.full_song import CHUNK_TARGET, MAX_SINGLE_CALL, plan_chunks

    short = [(5.0, 8.0), (10.0, 30.0)]
    assert plan_chunks(short, 60) == [(4.7, 30.5)]
    long = [(i * 10.0, i * 10.0 + 8.0) for i in range(70)]            # ~11.5 min of phrases
    chunks = plan_chunks(long, 720)
    assert len(chunks) >= 2 and all(b - a <= MAX_SINGLE_CALL for a, b in chunks)
    for (a, b), (c, _) in zip(chunks, chunks[1:]):
        assert b == c
        assert not any(s < b < e for s, e in long)                  # never cuts inside a phrase


def test_pitch_key_spelling():
    from auralis.voice.full_song import _pitch_key
    from auralis.voice.pitch import parse_key

    for key in ("G♯ minor", "D♭ major", "F♯ minor", "A♭ major"):
        parse_key(_pitch_key(key))                                   # must not raise


def _identity(src, dst, quality):
    shutil.copyfile(src, dst)


def test_sing_song_end_to_end_with_stand_in_voice(tmp_path):
    from auralis.generation import render_instrumental
    from auralis.voice import VoiceProfileStore
    from auralis.voice.full_song import sing_song

    bp = _short()
    render = render_instrumental(bp, str(tmp_path / "render"))
    store = VoiceProfileStore(tmp_path / "voices")
    ref = tmp_path / "ref.wav"
    t = np.arange(SR * 8) / SR
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * t) * (1 + 0.3 * np.sin(2 * np.pi * 0.5 * t))).astype(np.float32), SR)
    profile = store.create("Stand In", str(ref), True)
    out = sing_song(bp, render, profile, str(tmp_path / "song"), _identity, quality="fast")
    assert out["notes_sung"] > 20 and out["syllables"] > 20 and len(out["chunks"]) == 1
    for key in ("guide_path", "converted_path", "polished_path", "finished_path", "song_master_path"):
        assert (tmp_path / "song" / out[key].split("\\")[-1].split("/")[-1]).is_file(), key
    song, sr = sf.read(out["song_master_path"])
    assert song.ndim == 2 and abs(len(song) / sr - render["duration_seconds"]) < 2
    assert out["after_peak_db"] <= -0.9 and out["guide_sings_words"] is False


def test_api_sing_validates_and_runs(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main, projects
    from auralis.projects import ProjectStore
    from auralis.voice import VoiceProfileStore

    class Fake:
        def convert(self, source_path, output_path, **kw):
            shutil.copyfile(source_path, output_path)
            return {"output_path": output_path}

    store = VoiceProfileStore(tmp_path / "voices")
    ref = tmp_path / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(SR * 8) / SR)).astype(np.float32), SR)
    pid = store.create("Api Voice", str(ref), True).id
    monkeypatch.setattr(main, "VOICE_STORE", store)
    monkeypatch.setattr(main, "VOICE_PROVIDER", Fake())
    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    client = TestClient(main.app)
    bp = _short()
    assert client.post("/composer/sing", json={"blueprint": bp, "profile_id": "0" * 12}).status_code == 404
    assert client.post("/composer/sing", json={"blueprint": bp, "profile_id": pid, "quality": "loud"}).status_code == 422
    assert client.post("/composer/sing", json={"blueprint": bp, "profile_id": pid,
                                               "render_job_id": "nope"}).status_code == 404

    def wait(job_id):
        for _ in range(400):
            st = client.get(f"/jobs/{job_id}").json()
            if st["stage"] in ("done", "error"):
                return st
            time.sleep(0.5)
        raise AssertionError("timeout")

    render_id = client.post("/composer/render", json={"blueprint": bp}).json()["job_id"]
    assert wait(render_id)["stage"] == "done"
    other = dict(bp, id="f" * 12)
    assert client.post("/composer/sing", json={"blueprint": other, "profile_id": pid,
                                               "render_job_id": render_id}).status_code == 409
    job = client.post("/composer/sing", json={"blueprint": bp, "profile_id": pid, "render_job_id": render_id,
                                              "quality": "fast"}).json()["job_id"]
    st = wait(job)
    assert st["stage"] == "done", st
    for name in ("song", "vocal", "guide", "converted"):
        assert client.get(f"/composer/sing/{job}/file/{name}").status_code == 200, name
    proj = client.post("/projects", json={"name": "Sung Song"}).json()["id"]
    saved = client.post(f"/projects/{proj}/import-job", json={"job_id": job})
    assert saved.status_code == 200 and any(a["name"] == "song.wav" for a in saved.json()["assets"])
