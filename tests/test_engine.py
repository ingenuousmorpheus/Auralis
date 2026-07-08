"""Engine tests. Run with: pytest -q"""
import numpy as np
import soundfile as sf
import pytest

from auralis.engine.loudness import (
    measure,
    normalize,
    apply_true_peak_ceiling,
    normalize_with_limiter,
)
from auralis.engine.profiles_loader import list_profiles, load_profile
from auralis.engine.mastering import master_file


@pytest.fixture
def tone(tmp_path):
    sr = 44100
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    sig = 0.2 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 440 * t)
    stereo = np.stack([sig, sig * 0.95], axis=1).astype(np.float32) * 0.3
    p = tmp_path / "in.wav"
    sf.write(p, stereo, sr, subtype="PCM_24")
    return str(p), sr


def test_profiles_load():
    profs = list_profiles()
    assert len(profs) == 5
    ids = {p.id for p in profs}
    assert "neutral" in ids and "vocal-forward-rnb" in ids
    # naming policy: every profile must carry an inspired_by note
    assert all(p.inspired_by for p in profs)


def test_normalize_hits_target(tone):
    path, sr = tone
    audio, _ = sf.read(path, always_2d=True, dtype="float32")
    out = normalize(audio, sr, -14.0)
    after = measure(out, sr).integrated_lufs
    assert abs(after - (-14.0)) < 0.5  # within half a LU


def test_ceiling_respected(tone):
    path, sr = tone
    audio, _ = sf.read(path, always_2d=True, dtype="float32")
    loud = normalize(audio, sr, -6.0)            # push it up
    safe = apply_true_peak_ceiling(loud, sr, -1.0)
    assert measure(safe, sr).true_peak_db <= -1.0 + 0.05


def test_limiter_hits_loudness_and_true_peak():
    sr = 48000
    t = np.arange(sr * 3) / sr
    sig = 0.02 * np.sin(2 * np.pi * 220 * t)
    sig[::4800] = 0.95
    stereo = np.stack([sig, sig], axis=1).astype(np.float32)
    out = normalize_with_limiter(stereo, sr, -12.0, -1.0)
    stats = measure(out, sr)
    assert abs(stats.integrated_lufs - (-12.0)) < 0.35
    assert stats.true_peak_db <= -1.0 + 0.05


def test_master_end_to_end(tone, tmp_path):
    path, sr = tone
    out = str(tmp_path / "master.wav")
    res = master_file(path, out, load_profile("neutral"), target_lufs=-14.0)
    assert abs(res.after_lufs - (-14.0)) < 0.5
    assert res.after_peak_db <= -1.0 + 0.05
    assert res.mode in ("reference", "internal-target")


def test_character_profile_processes_audio(tone, tmp_path):
    path, _ = tone
    out = str(tmp_path / "warm.wav")
    res = master_file(path, out, load_profile("warm-soul"), target_lufs=-15.0)
    rendered, _ = sf.read(out, always_2d=True)
    original, _ = sf.read(path, always_2d=True)
    assert res.mode == "internal-target"
    assert rendered.shape == original.shape
    assert not np.allclose(rendered, original, atol=1e-4)


def test_reference_mode(tone, tmp_path):
    """A user-supplied reference should engage reference mode."""
    path, sr = tone
    # build a distinct reference track
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    ref = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.4 * np.sin(2 * np.pi * 3000 * t)
    ref_path = str(tmp_path / "ref.wav")
    sf.write(ref_path, np.stack([ref, ref], axis=1).astype(np.float32) * 0.6, sr, subtype="PCM_16")

    out = str(tmp_path / "master.wav")
    res = master_file(path, out, load_profile("neutral"),
                      target_lufs=-14.0, reference_path=ref_path)
    # Matchering may be absent in some CI envs; only assert mode when it ran.
    import auralis.engine.mastering as m
    if m.mg is not None:
        assert res.mode == "reference"
    assert abs(res.after_lufs - (-14.0)) < 0.5


# ── Phase 2 tests ──────────────────────────────────────────────────────────

def make_stems(tmp_path, sr=44100):
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    raw = {
        "vocal":    (0.3 * np.sin(2*np.pi*350*t)).astype(np.float32) * 0.3,
        "bass":     (0.6 * np.sin(2*np.pi*80*t)).astype(np.float32) * 0.4,
        "drums":    (np.random.randn(len(t)) * np.exp(-((t%0.5)*8))).astype(np.float32) * 0.35,
        "harmonic": (0.3*np.sin(2*np.pi*440*t)+0.3*np.sin(2*np.pi*880*t)).astype(np.float32) * 0.3,
    }
    paths = {}
    for role, sig in raw.items():
        p = str(tmp_path / f"{role}.wav")
        sf.write(p, np.stack([sig, sig*0.95], axis=1), sr)
        paths[role] = p
    return paths

def test_analysis_runs(tmp_path):
    from auralis.engine.analysis import analyse
    paths = make_stems(tmp_path)
    audio, sr = sf.read(paths["bass"], always_2d=True, dtype="float32")
    a = analyse(audio, sr, path=paths["bass"])
    assert a.role == "bass"
    assert -70 < a.integrated_lufs < 0
    assert len(a.band_energy) == 8


def test_filename_role_is_preferred(tmp_path):
    from auralis.engine.analysis import analyse
    sr = 44100
    audio = np.random.default_rng(7).normal(0, 0.01, (sr, 1)).astype(np.float32)
    a = analyse(audio, sr, path=str(tmp_path / "Lead_Vox.wav"))
    assert a.role == "vocal"
    assert a.role_confidence > 0.9

def test_mixer_produces_params(tmp_path):
    from auralis.engine.analysis import analyse
    from auralis.engine.mixer import mix
    paths = make_stems(tmp_path)
    analyses = []
    for p in paths.values():
        audio, sr = sf.read(p, always_2d=True, dtype="float32")
        analyses.append(analyse(audio, sr, path=p))
    params = mix(analyses, profile_id="vocal-forward-rnb")
    assert len(params) == 4
    assert all(hasattr(p, "gain_db") for p in params)
    assert all(p.highpass_hz > 0 for p in params)

def test_console_sums_to_stereo(tmp_path):
    from auralis.engine.analysis import analyse
    from auralis.engine.mixer import mix
    from auralis.engine.console import apply_and_sum
    paths = make_stems(tmp_path)
    audios, analyses = [], []
    for p in paths.values():
        audio, sr = sf.read(p, always_2d=True, dtype="float32")
        audios.append((audio, sr)); analyses.append(analyse(audio, sr, path=p))
    params = mix(analyses)
    out = str(tmp_path / "mix.wav")
    result = apply_and_sum(audios, params, out)
    mix_audio, _ = sf.read(out, always_2d=True)
    assert mix_audio.shape[1] == 2
    assert mix_audio.shape[0] > 0


def test_console_preserves_stereo_at_center(monkeypatch):
    import auralis.engine.console as console
    from auralis.engine.mixer import MixParams

    monkeypatch.setattr(console, "_PB", False)
    audio = np.stack([
        np.linspace(-0.5, 0.5, 1024, dtype=np.float32),
        np.linspace(0.4, -0.4, 1024, dtype=np.float32),
    ], axis=1)
    params = MixParams("stereo.wav", "other", 0.0, 0.0, highpass_hz=0.0)
    out = console._apply_chain(audio, 48000, params)
    assert np.allclose(out, audio, atol=1e-6)


def test_console_handles_mixed_sample_rates(tmp_path):
    from auralis.engine.console import apply_and_sum
    from auralis.engine.mixer import MixParams

    a = np.zeros((44100, 1), dtype=np.float32)
    b = np.zeros((48000, 1), dtype=np.float32)
    params = [
        MixParams("a.wav", "other", 0.0, 0.0),
        MixParams("b.wav", "other", 0.0, 0.0),
    ]
    out = str(tmp_path / "mixed_rates.wav")
    apply_and_sum([(a, 44100), (b, 48000)], params, out)
    rendered, sr = sf.read(out, always_2d=True)
    assert sr == 44100
    assert abs(len(rendered) - 44100) <= 2

def test_full_pipeline(tmp_path):
    from auralis.engine.pipeline import run
    paths = make_stems(tmp_path)
    out = str(tmp_path / "master.wav")
    result = run(stem_paths=list(paths.values()), output_path=out,
                 profile_id="neutral", target_lufs=-14.0)
    assert result.mode == "heuristic"
    assert abs(result.master_result["after_lufs"] - (-14.0)) < 0.5
    assert len(result.stem_analyses) == 4
    assert len(result.mix_params) == 4
    assert (tmp_path / "session.json").exists()
    assert (tmp_path / "report.md").exists()
