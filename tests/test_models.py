"""Model lifecycle + provider interfaces (no real heavy models: fakes and a stand-in worker)."""
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from auralis.models import (ManagedModel, ModelManager, ModelMemoryError, ModelNotInstalledError, ModelSpec,
                            Registry, SectionGenerator, SectionResult, SubprocessWorker, WorkerError)
from auralis.models.builtin import ACEStepSections, DiffSingerGuide, SeedVCConverter, VocaliseGuide


class FakeModel(ManagedModel):
    def __init__(self, model_id, kind="section_generator", resident=True, heavy=True, installed=True,
                 min_commit=0.0, commit=0.0, log=None):
        self.spec = ModelSpec(id=model_id, kind=kind, name=model_id.upper(), licence="test", heavy=heavy,
                              resident=resident, min_commit_gb=min_commit, commit_gb=commit)
        self._installed, self.loaded, self.log = installed, False, log if log is not None else []

    def is_installed(self):
        return self._installed

    def is_loaded(self):
        return self.loaded

    def load(self):
        self.loaded = True
        self.log.append(("load", self.spec.id))

    def unload(self):
        self.loaded = False
        self.log.append(("unload", self.spec.id))


def _manager(policy="balanced", memory=None):
    log = []
    m = ModelManager(memory=memory, policy=policy)
    a, b = FakeModel("a", log=log), FakeModel("b", log=log)
    m.register(a)
    m.register(b)
    return m, a, b, log


def test_balanced_loads_for_the_job_and_releases_after():
    m, a, b, log = _manager()
    with m.use("a") as model:
        assert model is a and a.loaded and m.status()["busy"] == "a"
    assert not a.loaded and m.status()["loaded"] == [] and m.status()["busy"] is None
    assert log == [("load", "a"), ("unload", "a")]


def test_switching_models_unloads_the_other_first():
    m, a, b, log = _manager(policy="keep_warm")
    with m.use("a"):
        pass
    assert a.loaded                                                    # kept warm
    with m.use("b"):
        assert b.loaded and not a.loaded                               # never both at once
    assert log == [("load", "a"), ("unload", "a"), ("load", "b")]
    assert m.release_all() == ["b"] and not b.loaded


def test_keep_warm_releases_after_idle_and_on_policy_change():
    m, a, b, log = _manager(policy="keep_warm")
    m.idle_seconds = 0.05
    with m.use("a"):
        pass
    time.sleep(0.1)
    m.status()                                                         # the idle sweep runs here
    assert not a.loaded
    with m.use("b"):
        pass
    assert b.loaded
    m.set_policy("balanced")
    assert not b.loaded


def test_one_job_at_a_time_across_threads_and_models():
    m, a, b, _ = _manager()
    running, peak = [0], [0]
    lock = threading.Lock()

    def job(mid):
        with m.use(mid):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            with lock:
                running[0] -= 1

    threads = [threading.Thread(target=job, args=("a" if i % 2 else "b",)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 1


def test_reentrant_same_model_but_not_a_different_one():
    m, a, b, log = _manager()
    with m.use("a"):
        with m.use("a"):
            assert a.loaded
        assert a.loaded                                                # still inside the outer job
        with pytest.raises(RuntimeError, match="one heavy model at a time"):
            with m.use("b"):
                pass
    assert not a.loaded


def test_memory_gate(monkeypatch):
    monkeypatch.delenv("AURALIS_MEMORY_CHECK", raising=False)
    m = ModelManager(memory=lambda: 4.0)
    m.register(FakeModel("big", min_commit=6.0, commit=9.0))
    with pytest.raises(ModelMemoryError, match="needs about 6 GB"):
        with m.use("big"):
            pass
    ok = ModelManager(memory=lambda: 7.0)
    ok.register(FakeModel("big", min_commit=6.0, commit=9.0))
    with ok.use("big"):
        pass
    strict = ModelManager(memory=lambda: 7.0, policy="low_memory")
    strict.register(FakeModel("big", min_commit=6.0, commit=9.0))
    with pytest.raises(ModelMemoryError, match="needs about 9 GB"):
        with strict.use("big"):
            pass
    unknown = ModelManager(memory=lambda: None)                       # memory unknown: never blocks
    unknown.register(FakeModel("big", min_commit=6.0))
    with unknown.use("big"):
        pass
    monkeypatch.setenv("AURALIS_MEMORY_CHECK", "off")
    with m.use("big"):
        pass


def test_memory_held_by_a_model_we_will_unload_counts_as_free(monkeypatch):
    monkeypatch.delenv("AURALIS_MEMORY_CHECK", raising=False)
    m = ModelManager(memory=lambda: 4.0, policy="keep_warm")
    m.register(FakeModel("warm", commit=5.0))
    m.register(FakeModel("next", min_commit=8.0))
    with m.use("warm"):
        pass
    with m.use("next"):                                                # 4 free + 5 reclaimed ≥ 8
        pass


def test_not_installed_is_refused():
    m = ModelManager(memory=None)
    m.register(FakeModel("missing", installed=False))
    with pytest.raises(ModelNotInstalledError):
        with m.use("missing"):
            pass


# ── the resident-worker protocol (a stand-in script, not a model) ───────────

WORKER = r'''
import json, sys
print("loading weights...", flush=True)
print(json.dumps({"ready": True, "model": "stand-in"}), flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("op") == "shutdown":
        break
    if msg["op"] == "echo":
        print(json.dumps({"id": msg["id"], "ok": True, "echo": msg["text"]}), flush=True)
    else:
        print(json.dumps({"id": msg["id"], "ok": False, "error": "unknown op"}), flush=True)
'''


def test_subprocess_worker_load_request_unload(tmp_path):
    script = tmp_path / "auralis_worker.py"
    script.write_text(WORKER, encoding="utf-8")
    w = SubprocessWorker(sys.executable, script, ready_timeout=30, request_timeout=30)
    assert w.start()["model"] == "stand-in" and w.running
    assert w.request("echo", text="hi")["echo"] == "hi"
    with pytest.raises(WorkerError, match="unknown op"):
        w.request("nope")
    proc = w._proc
    w.stop()
    assert not w.running and proc.poll() is not None                   # the process (and its memory) is gone
    with pytest.raises(WorkerError, match="not running"):
        w.request("echo", text="x")


def test_worker_that_fails_to_start_reports_why(tmp_path):
    script = tmp_path / "auralis_worker.py"
    script.write_text("import sys; sys.stderr.write('CUDA out of memory'); sys.exit(3)", encoding="utf-8")
    with pytest.raises(WorkerError, match="did not start.*CUDA out of memory"):
        SubprocessWorker(sys.executable, script, ready_timeout=30).start()


def test_planned_providers_plug_into_the_worker_lifecycle(tmp_path):
    """ACE-Step's adapter uses the same load/unload path once its folder exists: here a
    stand-in worker plays its part, proving the lifecycle without the real model."""
    root = tmp_path / "ace-step"
    (root / ".venv" / "Scripts").mkdir(parents=True)
    ace = ACEStepSections(root=root)
    assert not ace.is_installed()
    script = root / "auralis_worker.py"
    script.write_text(WORKER, encoding="utf-8")
    ace_python = root / ".venv" / "Scripts" / "python.exe"
    ace_python.write_bytes(Path(sys.executable).read_bytes()) if sys.platform == "win32" else None
    if sys.platform == "win32":
        assert ace.is_installed()
        m = ModelManager(memory=None)
        m.register(ace)
        with m.use("ace-step"):
            assert ace.is_loaded()
        assert not ace.is_loaded()                                     # balanced: released after the job


# ── registry ────────────────────────────────────────────────────────────────

class FakeConverter(ManagedModel):
    spec = ModelSpec(id="seed-vc", kind="voice_converter", name="Seed-VC", licence="GPL", heavy=True)


def test_registry_defaults_fallbacks_and_persistence(tmp_path):
    m = ModelManager(memory=None)
    reg = Registry(m, config_path=tmp_path / "models.json",
                   providers=[FakeConverter(), VocaliseGuide(), ACEStepSections(root=tmp_path / "none"),
                              DiffSingerGuide(root=tmp_path / "none2")])
    assert reg.guide_singer().spec.id == "vocalise"
    assert reg.section_generator() is None
    with pytest.raises(ValueError, match="not installed"):
        reg.select("guide_singer", "diffsinger")
    reg.choices["guide_singer"] = "diffsinger"                          # e.g. chosen, then uninstalled
    singer, why = reg.resolve("guide_singer")
    assert singer.spec.id == "vocalise" and "isn't installed" in why
    reg.set_policy("keep_warm")
    again = Registry(ModelManager(memory=None), config_path=tmp_path / "models.json",
                     providers=[FakeConverter(), VocaliseGuide()])
    assert again.manager.policy == "keep_warm"
    status = reg.status()
    assert status["kinds"]["section_generator"]["active"] is None
    assert {mm["id"] for mm in status["models"]} == {"seed-vc", "vocalise", "ace-step", "diffsinger"}


def test_seedvc_adapter_uses_the_shared_provider():
    class P:
        def status(self):
            return type("S", (), {"installed": False})()

    conv = SeedVCConverter()
    conv.provider_getter = lambda: P()
    assert not conv.is_installed()


# ── pipeline hooks ──────────────────────────────────────────────────────────

class ToneSections(SectionGenerator):
    spec = ModelSpec(id="tone-gen", kind="section_generator", name="Tone generator", licence="test",
                     heavy=True, resident=True)

    def __init__(self):
        self.loaded, self.calls = False, []

    def is_loaded(self):
        return self.loaded

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False

    def generate(self, request):
        assert self.loaded
        self.calls.append(request)
        n = int(request.seconds * 44100)
        path = f"{request.out_dir}/{request.section_id}.wav"
        sf.write(path, (0.2 * np.sin(2 * np.pi * 440 * np.arange(n) / 44100)).astype(np.float32), 44100)
        return SectionResult(paths={"mix": path}, sample_rate=44100, seconds=request.seconds, provider=self.spec.id)


def test_render_uses_a_section_generator_for_marked_sections_only(tmp_path, monkeypatch):
    from auralis.composer import build_blueprint, revise
    from auralis.generation import render_instrumental
    from auralis.models import MODELS

    gen = ToneSections()
    MODELS.register(gen)
    bp = build_blueprint("", voice_range=(50.0, 72.0), era="90s_rnb", key="C major", tempo=120)
    ids = {}
    for s in bp["sections"]:
        ids.setdefault(s["type"], s["id"])
    bp = revise(bp, {"sections": [{"id": ids["intro"], "bars": 2}, {"id": ids["verse"], "bars": 2},
                                  {"id": ids["chorus"], "bars": 2, "renderer": "tone-gen"}]})
    out = render_instrumental(bp, str(tmp_path / "r"), master=False, section_generator=gen)
    assert [c.section_id for c in gen.calls] == [ids["chorus"]]
    prompt = gen.calls[0].prompt
    assert "Chorus" in prompt and "no vocals" in prompt and "lead vocal" not in prompt
    assert not gen.loaded                                              # released after the job
    assert "generated" in out["stems"]
    y, sr = sf.read(out["stems"]["generated"])
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    a = int(chorus["start_seconds"] * sr)
    assert np.abs(y[:a]).max() < 1e-6 and np.abs(y[a:a + sr // 2]).max() > 0.1   # placed at the chorus
    none = render_instrumental(bp, str(tmp_path / "r2"), master=False, section_generator=None)
    assert none["generated_sections"][0]["rendered_by"] == "synth" and "generated" not in none["stems"]


def test_sing_song_uses_the_registry_guide_singer(tmp_path):
    from auralis.generation import render_instrumental
    from auralis.voice import VoiceProfileStore
    from auralis.voice.full_song import sing_song

    from test_full_song import _short

    class CountingSinger(VocaliseGuide):
        spec = ModelSpec(id="counting", kind="guide_singer", name="Counting", licence="test")

        def __init__(self):
            self.calls = 0

        def sing(self, score, total_seconds, seed=0):
            self.calls += 1
            return super().sing(score, total_seconds, seed)

    bp = _short()
    render = render_instrumental(bp, str(tmp_path / "r"), master=False)
    ref = tmp_path / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(44100 * 8) / 44100)).astype(np.float32), 44100)
    profile = VoiceProfileStore(tmp_path / "v").create("Stand In", str(ref), True)
    singer = CountingSinger()
    import shutil
    out = sing_song(bp, render, profile, str(tmp_path / "s"), lambda s, d, q: shutil.copyfile(s, d),
                    quality="fast", master=False, production="lead", singer=singer)
    assert singer.calls == 1 and out["guide_singer"] == "counting"


def test_api_engines(monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main

    client = TestClient(main.app)
    status = client.get("/models").json()
    assert status["kinds"]["voice_converter"]["options"] and "policies" in status
    assert client.post("/models/policy", json={"policy": "fast"}).status_code == 422
    assert client.post("/models/policy", json={"policy": "balanced"}).json()["policy"] == "balanced"
    assert client.post("/models/select", json={"kind": "guide_singer", "model_id": "diffsinger"}).status_code == 422
    assert client.post("/models/release").status_code == 200
