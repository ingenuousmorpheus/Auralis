import json
import time

import numpy as np
import pytest
import soundfile as sf

from auralis.projects import ProjectStore
from auralis.projects.jobs import job_kind, job_outputs


def _tone(path, seconds=2.0, sr=44100, freq=220.0, stereo=True):
    t = np.arange(int(sr * seconds)) / sr
    mono = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(path, np.stack([mono, mono], 1) if stereo else mono, sr)
    return str(path)


# ── Store ──────────────────────────────────────────────────────────────────

def test_project_is_created_with_folders_and_manifest(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create("Late Night Demo")
    project_dir = tmp_path / project.id
    for folder in ("sources", "stems", "vocals", "mixes", "masters", "reports", "generated"):
        assert (project_dir / folder).is_dir()
    manifest = json.loads((project_dir / "project.json").read_text("utf-8"))
    assert manifest["name"] == "Late Night Demo"
    assert manifest["status"] == "open"
    assert manifest["schema_version"] == 1
    assert [p.id for p in store.list()] == [project.id]


def test_project_name_is_required(tmp_path):
    with pytest.raises(ValueError):
        ProjectStore(tmp_path).create("  <>  ")


def test_asset_is_copied_and_source_left_untouched(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    source = _tone(tmp_path / "song.wav")
    before = open(source, "rb").read()
    project = store.create("Song")
    asset = store.add_asset(project.id, source, "source", origin={"type": "upload"})
    assert asset.path == "sources/song.wav"
    assert open(source, "rb").read() == before
    stored = store.asset_path(project.id, asset.id)
    assert stored.read_bytes() == before
    assert asset.size_bytes == len(before)
    # Same name again is kept, not overwritten.
    second = store.add_asset(project.id, source, "source")
    assert second.name != asset.name
    assert len(store.get(project.id).assets) == 2


def test_closed_project_rejects_new_assets_until_reopened(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    source = _tone(tmp_path / "vocal.wav")
    project = store.create("Song")
    store.close(project.id)
    assert store.get(project.id).status == "closed"
    with pytest.raises(PermissionError):
        store.add_asset(project.id, source, "vocal")
    store.open(project.id)
    store.add_asset(project.id, source, "vocal")
    actions = [event["action"] for event in store.get(project.id).history]
    assert actions == ["created", "closed", "opened", "asset added"]


def test_project_survives_a_new_store_instance(tmp_path):
    """The AU-01 gate at store level: close, 'restart', reopen, assets linked."""
    root = tmp_path / "projects"
    source = _tone(tmp_path / "mix.wav")
    store = ProjectStore(root)
    project = store.create("Persistent")
    asset = store.add_asset(project.id, source, "master")
    store.close(project.id)
    del store

    reopened_store = ProjectStore(root)
    reopened = reopened_store.open(project.id)
    assert reopened.status == "open"
    assert [a.id for a in reopened.assets] == [asset.id]
    assert reopened_store.verify(project.id, deep=True)["linked"] is True
    assert reopened_store.asset_path(project.id, asset.id).read_bytes() == open(source, "rb").read()


def test_verify_reports_missing_and_changed_assets(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create("Song")
    a = store.add_asset(project.id, _tone(tmp_path / "a.wav"), "stem")
    b = store.add_asset(project.id, _tone(tmp_path / "b.wav", freq=330), "stem")
    (tmp_path / "projects" / project.id / a.path).unlink()
    target = tmp_path / "projects" / project.id / b.path
    data = bytearray(target.read_bytes())
    data[-1] ^= 0xFF                      # same size, different content
    target.write_bytes(bytes(data))
    shallow = store.verify(project.id)
    assert shallow["missing"] == [a.id] and shallow["changed"] == []
    deep = store.verify(project.id, deep=True)
    assert deep["changed"] == [b.id] and deep["linked"] is False


def test_project_ids_are_validated(tmp_path):
    store = ProjectStore(tmp_path)
    for bad in ("../x", "..", "ABCDEF123456", "abc"):
        with pytest.raises(FileNotFoundError):
            store.get(bad)


def test_remove_asset_deletes_file_and_record(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create("Song")
    asset = store.add_asset(project.id, _tone(tmp_path / "v.wav"), "vocal")
    path = store.asset_path(project.id, asset.id)
    store.remove_asset(project.id, asset.id)
    assert not path.exists()
    assert store.get(project.id).assets == []


# ── Job → asset mapping ────────────────────────────────────────────────────

def test_master_job_maps_input_and_master_but_never_the_reference(tmp_path):
    job = {
        "stage": "done",
        "input": _tone(tmp_path / "input.wav"),
        "filename": "My Song.wav",
        "reference": _tone(tmp_path / "reference.wav"),
        "result": {"output_path": _tone(tmp_path / "master.wav"), "mode": "reference",
                   "profile_id": "neutral", "after_lufs": -14.0},
    }
    assert job_kind(job) == "master"
    outputs = job_outputs(job)
    assert [(o.kind, o.name) for o in outputs] == [("source", "My Song.wav"), ("master", "master.wav")]
    assert all("reference" not in o.path for o in outputs)
    assert outputs[1].metadata["profile_id"] == "neutral"


def test_mix_job_maps_stems_mix_master_and_reports(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("# report")
    session = tmp_path / "session.json"
    session.write_text("{}")
    job = {
        "stage": "done",
        "stems": [{"filename": "vocal.wav", "path": _tone(tmp_path / "s1.wav")},
                  {"filename": "bass.wav", "path": _tone(tmp_path / "s2.wav")}],
        "result": {"stem_analyses": [], "mix_path": _tone(tmp_path / "pre.wav"),
                   "master_path": _tone(tmp_path / "m.wav"),
                   "report_path": str(report), "session_path": str(session),
                   "master_result": {"after_lufs": -14.0, "profile_id": "neutral"}},
    }
    assert job_kind(job) == "mix"
    kinds = [(o.kind, o.name) for o in job_outputs(job)]
    assert kinds == [("stem", "vocal.wav"), ("stem", "bass.wav"), ("mix", "pre_master.wav"),
                     ("master", "master.wav"), ("report", "mix_report.md"),
                     ("report", "mix_session.json")]


def test_unfinished_and_non_audio_jobs_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        job_outputs({"stage": "running", "result": None})
    with pytest.raises(ValueError):
        job_outputs({"stage": "done", "kind": "voice-training",
                     "result": {"checkpoint_path": "x"}})


def test_missing_job_files_are_reported(tmp_path):
    with pytest.raises(ValueError, match="no longer available"):
        job_outputs({"stage": "done", "kind": "pitch-polish",
                     "result": {"output_path": str(tmp_path / "gone.wav")}})


# ── API: the AU-01 gate end to end ─────────────────────────────────────────

def test_api_master_job_saved_to_project_survives_restart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main, projects

    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    client = TestClient(main.app)

    mix = _tone(tmp_path / "mix.wav", seconds=4.0)
    with open(mix, "rb") as handle:
        job_id = client.post("/upload", files={"file": ("mix.wav", handle, "audio/wav")}).json()["job_id"]
    assert client.post("/master", json={"job_id": job_id, "profile_id": "neutral"}).status_code == 200
    for _ in range(300):
        status = client.get(f"/jobs/{job_id}").json()
        if status["stage"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert status["stage"] == "done", status

    project = client.post("/projects", json={"name": "Gate Song"}).json()
    pid = project["id"]
    imported = client.post(f"/projects/{pid}/import-job", json={"job_id": job_id})
    assert imported.status_code == 200, imported.text
    assets = imported.json()["assets"]
    assert {a["kind"] for a in assets} == {"source", "master"}
    assert client.post(f"/projects/{pid}/import-job", json={"job_id": job_id}).status_code == 409
    master_bytes = client.get(f"/download/{job_id}").content

    assert client.post(f"/projects/{pid}/close").json()["status"] == "closed"
    assert client.post(f"/projects/{pid}/import-job", json={"job_id": job_id}).status_code == 409

    # Simulate a backend restart: in-memory jobs vanish, the store is rebuilt from disk.
    monkeypatch.setattr(main, "JOBS", {})
    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    assert client.get(f"/jobs/{job_id}").status_code == 404

    listed = client.get("/projects").json()
    assert [(p["id"], p["status"], p["asset_count"]) for p in listed] == [(pid, "closed", 2)]
    reopened = client.post(f"/projects/{pid}/open").json()
    assert reopened["status"] == "open"
    assert reopened["integrity"]["linked"] is True
    master_asset = next(a for a in reopened["assets"] if a["kind"] == "master")
    assert master_asset["origin"]["job_id"] == job_id
    downloaded = client.get(f"/projects/{pid}/assets/{master_asset['id']}")
    assert downloaded.status_code == 200
    assert downloaded.content == master_bytes


def test_api_rejects_bad_kinds_and_unknown_projects(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main, projects

    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    client = TestClient(main.app)
    assert client.get("/projects/000000000000").status_code == 404
    assert client.post("/projects", json={"name": ""}).status_code == 422
    pid = client.post("/projects", json={"name": "Song"}).json()["id"]
    with open(_tone(tmp_path / "a.wav"), "rb") as handle:
        bad = client.post(f"/projects/{pid}/assets", data={"kind": "nonsense"},
                          files={"file": ("a.wav", handle, "audio/wav")})
    assert bad.status_code == 422
    with open(_tone(tmp_path / "a.wav"), "rb") as handle:
        ok = client.post(f"/projects/{pid}/assets", data={"kind": "source"},
                         files={"file": ("a.wav", handle, "audio/wav")})
    assert ok.status_code == 200 and ok.json()["path"] == "sources/a.wav"
    assert client.post(f"/projects/{pid}/import-job", json={"job_id": "nope"}).status_code == 404
