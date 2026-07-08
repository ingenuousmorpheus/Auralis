import json

import numpy as np
import soundfile as sf

from auralis.voice.finish import (
    analyze_vocal,
    apply_module_overrides,
    decide_finish,
    finish_vocal,
)


def make_vocal(sr=44100, seconds=3):
    t = np.arange(sr * seconds) / sr
    carrier = (
        0.12 * np.sin(2 * np.pi * 220 * t)
        + 0.05 * np.sin(2 * np.pi * 440 * t)
        + 0.025 * np.sin(2 * np.pi * 3300 * t)
    )
    # Short high-frequency consonant-like bursts.
    noise = np.random.default_rng(9).normal(0, 0.025, len(t))
    gate = ((t % 0.45) < 0.035).astype(np.float32)
    return (carrier + noise * gate).astype(np.float32)[:, np.newaxis]


def make_instrumental(sr=44100, seconds=3):
    t = np.arange(sr * seconds) / sr
    left = 0.09 * np.sin(2 * np.pi * 110 * t) + 0.05 * np.sin(2 * np.pi * 880 * t)
    right = 0.08 * np.sin(2 * np.pi * 110 * t) + 0.05 * np.sin(2 * np.pi * 660 * t)
    return np.stack([left, right], axis=1).astype(np.float32)


def test_finish_decision_uses_serial_compression():
    vocal = make_vocal()
    analysis = analyze_vocal(vocal, 44100)
    decision = decide_finish(analysis, "polished-pop", 0.8)
    assert decision.leveling_ratio > 1.0
    assert decision.peak_ratio > decision.leveling_ratio
    assert any("Two light compression stages" in reason for reason in decision.reasons)


def test_module_overrides_clamp_bypass_and_annotate():
    vocal = make_vocal()
    analysis = analyze_vocal(vocal, 44100)
    decision = decide_finish(analysis, "polished-pop", 0.8)
    decision = apply_module_overrides(decision, {
        "eq": {"enabled": True, "presence_db": 99.0},   # clamped to max
        "saturation": {"enabled": False},               # bypassed
        "space": {"ambience_mix": 0.2},
        "bogus-module": {"enabled": False},             # ignored
    })
    assert decision.presence_db == 6.0
    assert decision.saturation_drive_db == 0.0
    assert decision.ambience_mix == 0.2
    assert any("Manual rack settings" in reason for reason in decision.reasons)


def test_module_overrides_none_is_identity():
    vocal = make_vocal()
    analysis = analyze_vocal(vocal, 44100)
    decision = decide_finish(analysis, "natural", 0.5)
    before = dict(decision.__dict__)
    after = apply_module_overrides(decision, None)
    assert dict(after.__dict__) == before


def test_vocal_finish_renders_vocal_preview_and_report(tmp_path):
    vocal_path = tmp_path / "vocal.wav"
    instrumental_path = tmp_path / "instrumental.wav"
    output_path = tmp_path / "finished.wav"
    preview_path = tmp_path / "preview.wav"
    report_path = tmp_path / "report.json"
    sf.write(vocal_path, make_vocal(), 44100)
    sf.write(instrumental_path, make_instrumental(), 44100)

    result = finish_vocal(
        str(vocal_path),
        str(output_path),
        preset="smooth-rnb",
        intensity=0.75,
        instrumental_path=str(instrumental_path),
        preview_path=str(preview_path),
        report_path=str(report_path),
    )

    assert output_path.exists()
    assert preview_path.exists()
    assert report_path.exists()
    finished, sr = sf.read(output_path, always_2d=True)
    assert sr == 44100
    assert finished.shape[1] == 2
    assert np.max(np.abs(finished)) <= 1.0
    report = json.loads(report_path.read_text("utf-8"))
    assert report["decision"]["preset"] == "smooth-rnb"
    assert report["analysis"]["instrumental_lufs"] is not None
    assert result["preview_path"] == str(preview_path)
