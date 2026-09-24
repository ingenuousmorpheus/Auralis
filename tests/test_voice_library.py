"""My Voice library: voices from a microphone take, voice cards, conversion history, engine lock."""
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from auralis.voice import VoiceProfileStore
from auralis.voice.capture import analyse_take
from auralis.voice.history import VoiceHistoryStore

SR = 48000


def _sing(seconds=40.0, noise=0.001, amp=0.3, low=57, high=69, seed=0):
    """A synthetic singer: 2–4 s phrases on scale notes between ``low`` and
    ``high`` (MIDI), with harmonics, vibrato and breaths in between."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * SR), np.float32)
    t0 = 0.4
    notes = [p for p in range(low, high + 1) if p % 12 in (0, 2, 4, 5, 7, 9, 11)]
    while t0 < seconds - 2:
        length = rng.uniform(2.0, 4.0)
        n = int(min(length, seconds - t0) * SR)
        t = np.arange(n) / SR
        pitch = notes[rng.integers(len(notes))]
        f = 440 * 2 ** ((pitch - 69) / 12) * (1 + 0.01 * np.sin(2 * np.pi * 5.5 * t))
        ph = 2 * np.pi * np.cumsum(f) / SR
        tone = np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)
        env = np.minimum(1, t / 0.05) * np.minimum(1, (t[-1] - t) / 0.08 + 1e-3)
        a = int(t0 * SR)
        out[a:a + n] += (amp / 1.75 * tone * env).astype(np.float32)
        t0 += length + rng.uniform(0.3, 0.7)
    out += (noise * rng.standard_normal(len(out))).astype(np.float32)
    return out


def _write(path, audio, sr=SR):
    sf.write(str(path), audio, sr, subtype="PCM_16")
    return str(path)


# ── Take analysis ──────────────────────────────────────────────────────────

def test_clean_take_is_usable_and_picks_a_sung_reference():
    audio = _sing(40)
    r = analyse_take(audio, SR)
    assert r.usable and r.quality in ("good", "great")
    assert 25 <= r.singing_seconds <= 40
    assert 6 <= r.reference_end - r.reference_start <= 20
    assert r.snr_db > 30 and not r.issues


@pytest.mark.parametrize("kind,expect", [
    ("clipped", "clips"), ("noisy", "noisy"), ("short", "Only"), ("quiet", "quiet"),
])
def test_bad_takes_explain_what_to_fix(kind, expect):
    if kind == "clipped":
        audio = np.clip(_sing(30) * 6, -1, 1)
    elif kind == "noisy":
        audio = _sing(30, noise=0.05)
    elif kind == "short":
        audio = _sing(4)
    else:
        audio = _sing(30, amp=0.004, noise=0.00002)
    r = analyse_take(audio, SR)
    text = " ".join(r.issues)
    assert expect in text and r.tips
    if kind in ("clipped", "short"):
        assert not r.usable and r.quality == "retake"


# ── Saving a voice from a take ─────────────────────────────────────────────

def test_voice_from_take_is_saved_with_range_dataset_and_consent(tmp_path):
    store = VoiceProfileStore(tmp_path / "voices")
    take = _write(tmp_path / "take.wav", _sing(45, low=55, high=67))
    consent = _write(tmp_path / "consent.wav", _sing(4))
    profile, report = store.create_from_take("Friend Voice", take, True, singer_name="Test Singer",
                                             consent_clip_path=consent)
    assert report["usable"]
    assert profile.created_via == "microphone" and profile.singer_name == "Test Singer"
    assert profile.consent_at and profile.consent_clip and profile.take_count == 1
    assert 6 <= profile.duration_seconds <= 20                   # reference window
    assert profile.dataset_clip_count > 3 and profile.kind == "studio-dataset"
    assert 53 <= profile.pitch_low_midi <= 58 and 64 <= profile.pitch_high_midi <= 69
    folder = tmp_path / "voices" / profile.id
    assert (folder / "consent.wav").is_file() and (folder / "takes" / "take_001.wav").is_file()
    assert "consent" not in " ".join(p.name for p in (folder / "dataset").iterdir())
    public = profile.public_dict()
    assert "reference_path" not in public and public["last_take"]["usable"]
    # a second take grows the dataset
    more = store.add_take(profile.id, _write(tmp_path / "take2.wav", _sing(30, seed=2)))
    assert more.take_count == 2 and more.dataset_clip_count > profile.dataset_clip_count
    assert store.rename(profile.id, "Renamed Voice").name == "Renamed Voice"


def test_take_needs_consent_and_quality(tmp_path):
    store = VoiceProfileStore(tmp_path / "voices")
    take = _write(tmp_path / "take.wav", _sing(30))
    with pytest.raises(ValueError, match="agree"):
        store.create_from_take("No Consent", take, False)
    with pytest.raises(ValueError, match="can't make a good voice"):
        store.create_from_take("Clipped", _write(tmp_path / "c.wav", np.clip(_sing(30) * 6, -1, 1)), True)
    assert store.list() == []


def test_old_profiles_still_load(tmp_path):
    store = VoiceProfileStore(tmp_path / "voices")
    profile = store.create("Old Style", _write(tmp_path / "r.wav", _sing(10)), True)
    folder = tmp_path / "voices" / profile.id
    import json
    data = json.loads((folder / "profile.json").read_text("utf-8"))
    for key in ("created_at", "created_via", "singer_name", "consent_at", "consent_clip", "take_count", "last_take"):
        data.pop(key)
    (folder / "profile.json").write_text(json.dumps(data), encoding="utf-8")
    assert store.get(profile.id).created_via == "upload"


# ── History ────────────────────────────────────────────────────────────────

def test_history_keeps_takes_across_store_instances(tmp_path):
    store = VoiceProfileStore(tmp_path / "voices")
    profile = store.create("History Voice", _write(tmp_path / "r.wav", _sing(10)), True)
    out = _write(tmp_path / "out.wav", _sing(8, seed=3))
    guide = _write(tmp_path / "guide.wav", _sing(8, seed=4))
    history = VoiceHistoryStore(tmp_path / "voices")
    item = history.add(profile.id, out, input_path=guide, input_name="guide.wav",
                       settings={"quality": "studio", "semitone_shift": 2, "output_path": "x"})
    assert item["settings"] == {"quality": "studio", "semitone_shift": 2}
    again = VoiceHistoryStore(tmp_path / "voices")               # a restart
    assert [i["id"] for i in again.list(profile.id)] == [item["id"]]
    assert again.path(profile.id, item["id"], "input").suffix == ".wav"
    peaks = again.peaks(profile.id, item["id"])
    assert 100 < len(peaks) <= 600 and max(peaks) == 1.0
    assert again.update(profile.id, item["id"], rating=1, note="nice")["rating"] == 1
    with pytest.raises(ValueError):
        again.update(profile.id, item["id"], rating=5)
    again.delete(profile.id, item["id"])
    assert again.list(profile.id) == []


# ── API ────────────────────────────────────────────────────────────────────

class FakeProvider:
    """Stands in for Seed-VC: copies the guide and records how many run at once."""
    def __init__(self):
        self.running = 0
        self.max_running = 0
        self.lock = threading.Lock()

    def convert(self, source_path, output_path, progress=None, **kw):
        with self.lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        time.sleep(0.3)
        audio, sr = sf.read(source_path)
        sf.write(output_path, audio, sr)
        with self.lock:
            self.running -= 1
        return {"output_path": output_path, "provider": "fake", "quality": kw.get("quality"),
                "semitone_shift": kw.get("semitone_shift")}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from auralis.api import main, projects
    from auralis.projects import ProjectStore

    monkeypatch.setattr(main, "VOICE_STORE", VoiceProfileStore(tmp_path / "voices"))
    fake = FakeProvider()
    monkeypatch.setattr(main, "VOICE_PROVIDER", fake)
    monkeypatch.setattr(projects, "PROJECT_STORE", ProjectStore(tmp_path / "projects"))
    c = TestClient(main.app)
    c.fake = fake
    return c


def _wait(client, job_id):
    for _ in range(100):
        st = client.get(f"/jobs/{job_id}").json()
        if st["stage"] in ("done", "error"):
            return st
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_api_take_to_voice_to_conversion_history(client, tmp_path):
    take = _write(tmp_path / "take.wav", _sing(35))
    with open(take, "rb") as f:
        check = client.post("/voice/takes/check", files={"file": ("take.wav", f, "audio/wav")})
    assert check.status_code == 200 and check.json()["usable"]
    with open(take, "rb") as f:
        r = client.post("/voice/profiles/from-take", data={"name": "Mic Voice", "consent_confirmed": "true",
                                                           "singer_name": "Guest"},
                        files={"file": ("take.wav", f, "audio/wav")})
    assert r.status_code == 200, r.text
    pid = r.json()["profile"]["id"]
    assert r.json()["profile"]["created_via"] == "microphone"
    assert client.get(f"/voice/profiles/{pid}/reference").status_code == 200
    assert client.patch(f"/voice/profiles/{pid}", json={"name": "Guest Voice"}).json()["name"] == "Guest Voice"
    with open(take, "rb") as f:
        bad = client.post("/voice/profiles/from-take", data={"name": "X", "consent_confirmed": "false"},
                          files={"file": ("take.wav", f, "audio/wav")})
    assert bad.status_code == 422

    # conversions are kept in the voice's history
    guide = _write(tmp_path / "guide.wav", _sing(5, seed=9))
    with open(guide, "rb") as f:
        job = client.post("/voice/convert", data={"profile_id": pid, "quality": "fast"},
                          files={"file": ("guide.wav", f, "audio/wav")}).json()["job_id"]
    st = _wait(client, job)
    assert st["stage"] == "done", st
    items = client.get("/voice/history", params={"profile_id": pid}).json()
    assert len(items) == 1 and items[0]["input_name"] == "guide.wav"
    tid = items[0]["id"]
    assert client.get(f"/voice/history/{pid}/{tid}/audio").status_code == 200
    assert client.get(f"/voice/history/{pid}/{tid}/audio", params={"which": "input"}).status_code == 200
    assert len(client.get(f"/voice/history/{pid}/{tid}/peaks").json()) > 50
    assert client.patch(f"/voice/history/{pid}/{tid}", json={"rating": -1}).json()["rating"] == -1
    proj = client.post("/projects", json={"name": "Vocal Test"}).json()["id"]
    assert client.post(f"/voice/history/{pid}/{tid}/to-project", json={"project_id": proj}).status_code == 200
    assert client.delete(f"/voice/history/{pid}/{tid}").status_code == 200
    assert client.get("/voice/history").json() == []


def test_conversions_never_run_two_at_once(client, tmp_path):
    take = _write(tmp_path / "take.wav", _sing(30))
    with open(take, "rb") as f:
        pid = client.post("/voice/profiles/from-take", data={"name": "Queue Voice", "consent_confirmed": "true"},
                          files={"file": ("take.wav", f, "audio/wav")}).json()["profile"]["id"]
    guide = _write(tmp_path / "guide.wav", _sing(3, seed=5))
    jobs = []
    for _ in range(3):
        with open(guide, "rb") as f:
            jobs.append(client.post("/voice/convert", data={"profile_id": pid},
                                    files={"file": ("guide.wav", f, "audio/wav")}).json()["job_id"])
    assert all(_wait(client, j)["stage"] == "done" for j in jobs)
    assert client.fake.max_running == 1
    assert len(client.get("/voice/history", params={"profile_id": pid}).json()) == 3
