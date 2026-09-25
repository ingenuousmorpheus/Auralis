"""AU-10 automatic song assembly: one prompt → finished WAV in a project, editable stems, remix."""
import shutil
import time

import numpy as np
import pytest
import soundfile as sf

from auralis.composer.assemble import remix_project, remix_stems, save_song_to_project
from auralis.projects import ProjectStore

from test_full_song import _short


def _identity(src, dst, q):
    shutil.copyfile(src, dst)


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    """One short song, rendered and sung with a stand-in voice (shared by the tests)."""
    from auralis.generation import render_instrumental
    from auralis.voice import VoiceProfileStore
    from auralis.voice.full_song import sing_song

    tmp = tmp_path_factory.mktemp("song")
    bp = _short()
    render = render_instrumental(bp, str(tmp / "r"))
    ref = tmp / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(44100 * 8) / 44100)).astype(np.float32), 44100)
    profile = VoiceProfileStore(tmp / "v").create("Stand In", str(ref), True)
    song = sing_song(bp, render, profile, str(tmp / "song"), _identity, quality="fast")
    return bp, render, song


def test_song_is_saved_with_blueprint_and_tagged_stems(made, tmp_path):
    bp, render, song = made
    store = ProjectStore(tmp_path / "p")
    saved = save_song_to_project(store, "Assembled", bp, render, song)
    pid = saved["project_id"]
    assert store.blueprint(pid)["id"] == bp["id"]
    project = store.get(pid)
    parts = {a.metadata.get("part"): a for a in project.assets}
    for part in ("drums", "bass", "keys", "lead_vocal", "backing_vocals", "song_master", "midi"):
        assert part in parts, part
    assert parts["lead_vocal"].metadata["mix_role"] == "vocal"
    assert parts["backing_vocals"].metadata["mix_role"] == "other"
    assert parts["song_master"].kind == "master"
    mixable = {a.metadata["part"] for a in remix_stems(store, pid)}
    assert "lead_vocal" in mixable and "drums" in mixable
    assert not any(p.startswith("bv_") for p in mixable)            # single parts are kept, not remixed twice
    assert store.verify(pid, deep=True)["linked"]


def test_remix_from_project_stems_mute_solo_levels(made, tmp_path):
    bp, render, song = made
    store = ProjectStore(tmp_path / "p")
    pid = save_song_to_project(store, "Remix Me", bp, render, song)["project_id"]
    stems = {a.metadata["part"]: a.id for a in remix_stems(store, pid)}
    out = remix_project(store, pid, {stems["drums"]: {"mute": True}, stems["lead_vocal"]: {"gain_db": 2.0}},
                        str(tmp_path / "w"))
    used = {s["part"] for s in out["stems"]}
    assert "drums" not in used and "lead_vocal" in used and out["after_peak_db"] <= -0.9
    masters = [a for a in store.get(pid).assets if a.kind == "master"]
    assert any(m.id == out["master_asset_id"] for m in masters) and len(masters) >= 2
    solo = remix_project(store, pid, {stems["lead_vocal"]: {"solo": True}, stems["drums"]: {"mute": True}},
                         str(tmp_path / "w2"))
    assert [s["part"] for s in solo["stems"]] == ["lead_vocal"]
    assert solo["name"] == "remix_02.wav"
    with pytest.raises(ValueError, match="muted"):
        remix_project(store, pid, {sid: {"mute": True} for sid in stems.values()}, str(tmp_path / "w3"))
    # survives a restart: a new store instance can remix the same project
    again = remix_project(ProjectStore(tmp_path / "p"), pid, {}, str(tmp_path / "w4"))
    assert len(again["stems"]) == len(stems)


def test_gate_one_prompt_to_finished_song_api(tmp_path, monkeypatch):
    """AU-10 gate through the API: one request → project with a finished WAV and editable stems."""
    from fastapi.testclient import TestClient

    from auralis.api import main, projects
    from auralis.voice import VoiceProfileStore

    class Fake:
        def convert(self, source_path, output_path, **kw):
            shutil.copyfile(source_path, output_path)
            return {"output_path": output_path}

    store = VoiceProfileStore(tmp_path / "voices")
    ref = tmp_path / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(44100 * 8) / 44100)).astype(np.float32), 44100)
    pid_voice = store.create("Api Voice", str(ref), True).id
    monkeypatch.setattr(main, "VOICE_STORE", store)
    monkeypatch.setattr(main, "VOICE_PROVIDER", Fake())
    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    client = TestClient(main.app)
    assert client.post("/composer/song", json={"prompt": "x", "profile_id": "0" * 12}).status_code == 404
    assert client.post("/composer/song", json={"prompt": "x", "production": "choir"}).status_code == 422
    body = {"prompt": "short uptempo 2000s R&B", "lyrics": "[Verse]\nsing it now\n[Chorus]\nhold on tonight",
            "tempo": 120, "length_seconds": 45, "use_dna": False, "profile_id": pid_voice,
            "production": "doubles", "quality": "fast", "project_name": "Gate Song"}
    job = client.post("/composer/song", json=body).json()["job_id"]
    for _ in range(600):
        st = client.get(f"/jobs/{job}").json()
        if st["stage"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["stage"] == "done", st.get("error")
    res = st["result"]
    assert res["sung"] and res["voice"] == "Api Voice"
    project = client.get(f"/projects/{res['project_id']}").json()
    assert project["name"] == "Gate Song"
    master = next(a for a in project["assets"] if a["kind"] == "master")
    wav = client.get(f"/projects/{res['project_id']}/assets/{master['id']}")
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"                  # downloadable finished WAV
    stems = client.get(f"/projects/{res['project_id']}/stems").json()
    assert {"lead_vocal", "drums"} <= {s["part"] for s in stems}                    # editable stems kept
    r = client.post(f"/projects/{res['project_id']}/remix",
                    json={"levels": {stems[0]["asset_id"]: {"gain_db": -3}}}).json()["job_id"]
    for _ in range(300):
        rs = client.get(f"/jobs/{r}").json()
        if rs["stage"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert rs["stage"] == "done", rs
    assert client.get(f"/projects/{res['project_id']}/blueprint").status_code == 200
