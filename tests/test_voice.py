import json

import numpy as np
import pytest
import soundfile as sf

from auralis.voice.profiles import VoiceProfileStore, prepare_reference
from auralis.voice.seed_vc import SeedVCProvider


def make_voice(path, seconds=5.0, sr=44100):
    t = np.arange(int(sr * seconds)) / sr
    # A modest harmonic stack behaves more like a pitched voice than a sine.
    audio = (
        0.10 * np.sin(2 * np.pi * 220 * t)
        + 0.04 * np.sin(2 * np.pi * 440 * t)
        + 0.02 * np.sin(2 * np.pi * 660 * t)
    ).astype(np.float32)
    sf.write(path, audio, sr)


def test_voice_profile_is_private_and_reusable(tmp_path):
    source = tmp_path / "my_voice.wav"
    make_voice(source)
    store = VoiceProfileStore(tmp_path / "profiles")

    profile = store.create("My Voice", str(source), consent_confirmed=True)
    assert profile.duration_seconds == pytest.approx(5.0, abs=0.1)
    assert profile.peak_dbfs <= -2.9
    assert store.get(profile.id).name == "My Voice"
    assert "reference_path" not in profile.public_dict()
    assert len(store.list()) == 1

    metadata = json.loads(
        (tmp_path / "profiles" / profile.id / "profile.json").read_text("utf-8")
    )
    assert metadata["consent_confirmed"] is True


def test_voice_profile_requires_consent(tmp_path):
    source = tmp_path / "voice.wav"
    make_voice(source)
    store = VoiceProfileStore(tmp_path / "profiles")
    with pytest.raises(ValueError, match="permission"):
        store.create("Not Allowed", str(source), consent_confirmed=False)


def test_reference_rejects_clipping():
    audio = np.ones((44100 * 4, 1), dtype=np.float32)
    with pytest.raises(ValueError, match="clipping"):
        prepare_reference(audio, 44100)


def test_seed_provider_status_isolated(tmp_path):
    provider = SeedVCProvider(tmp_path / "seed-vc")
    status = provider.status()
    assert status.installed is False
    assert "GPL-3.0" in status.license


def test_studio_dataset_is_segmented_and_scored(tmp_path):
    source = tmp_path / "voice.wav"
    make_voice(source, seconds=5.0)
    store = VoiceProfileStore(tmp_path / "profiles")
    profile = store.create("Studio Voice", str(source), consent_confirmed=True)

    long_source = tmp_path / "long_take.wav"
    sr = 44100
    phrase = np.sin(2 * np.pi * 180 * np.arange(sr * 3) / sr).astype(np.float32) * 0.08
    silence = np.zeros(sr, dtype=np.float32)
    sf.write(long_source, np.concatenate([phrase, silence, phrase]), sr)
    updated = store.add_recordings(profile.id, [str(long_source)])

    assert updated.kind == "studio-dataset"
    assert updated.dataset_clip_count >= 2
    assert updated.dataset_duration_seconds >= 5.5
    assert updated.readiness_score >= 0
    assert store.dataset_dir(profile.id).exists()


def test_mark_studio_training(tmp_path):
    source = tmp_path / "voice.wav"
    make_voice(source)
    store = VoiceProfileStore(tmp_path / "profiles")
    profile = store.create("Studio Voice", str(source), consent_confirmed=True)
    checkpoint = tmp_path / "model.pth"
    config = tmp_path / "config.yml"
    checkpoint.write_bytes(b"model")
    config.write_text("config", encoding="utf-8")

    updated = store.mark_training(
        profile.id,
        status="trained",
        steps=1000,
        checkpoint_path=str(checkpoint),
        config_path=str(config),
    )
    assert updated.kind == "studio-trained"
    assert updated.training_steps == 1000
