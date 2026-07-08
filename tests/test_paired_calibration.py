import numpy as np
import soundfile as sf

from auralis.voice.paired import ingest_paired_calibration


def melody(sr=22050, stretch=1.0):
    parts = []
    for midi in [60, 62, 64, 67, 64, 62, 60] * 2:
        seconds = 1.1 * stretch
        t = np.arange(int(sr * seconds)) / sr
        frequency = 440 * 2 ** ((midi - 69) / 12)
        envelope = np.minimum(t / 0.03, 1) * np.minimum((seconds - t) / 0.04, 1)
        parts.append((0.1 * np.sin(2 * np.pi * frequency * t) * envelope).astype(np.float32))
        parts.append(np.zeros(int(sr * 0.12 * stretch), dtype=np.float32))
    return np.concatenate(parts)


def test_paired_calibration_accepts_matching_performances(tmp_path):
    guide = tmp_path / "guide.wav"
    singer = tmp_path / "singer.wav"
    sf.write(guide, melody(), 22050)
    # Same melody with a slight natural timing difference and changed timbre.
    target = melody(stretch=1.03)
    target += 0.025 * np.sin(
        2 * np.pi * 880 * np.arange(len(target)) / 22050
    ).astype(np.float32)
    sf.write(singer, target, 22050)

    report = ingest_paired_calibration(
        str(guide), str(singer), tmp_path / "profile", "Test Pair"
    )
    assert report["clip_count"] >= 1
    assert report["median_melodic_similarity"] > 0.68
    assert 0.82 <= report["timing_slope"] <= 1.18
    assert report["usable_singer_seconds"] > 5


def test_paired_calibration_rejects_unrelated_audio(tmp_path):
    guide = tmp_path / "guide.wav"
    singer = tmp_path / "singer.wav"
    sf.write(guide, melody(), 22050)
    rng = np.random.default_rng(3)
    sf.write(singer, rng.normal(0, 0.03, len(melody())).astype(np.float32), 22050)
    try:
        ingest_paired_calibration(str(guide), str(singer), tmp_path / "profile")
    except ValueError as exc:
        assert "same performance" in str(exc) or "no clean phrase" in str(exc)
    else:
        raise AssertionError("Unrelated audio should not pass paired calibration")
