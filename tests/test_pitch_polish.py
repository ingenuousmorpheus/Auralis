import json

import librosa
import numpy as np
import soundfile as sf

from auralis.voice.pitch import detect_key, parse_key, pitch_polish


def sine_note(midi, seconds, sr=44100, cents=0):
    frequency = librosa.midi_to_hz(midi + cents / 100)
    t = np.arange(int(sr * seconds)) / sr
    envelope = np.minimum(t / 0.04, 1.0) * np.minimum((seconds - t) / 0.05, 1.0)
    vibrato = 0.12 * np.sin(2 * np.pi * 5.2 * t)
    phase = 2 * np.pi * np.cumsum(frequency * 2 ** (vibrato / 12)) / sr
    return (0.12 * np.sin(phase) * envelope).astype(np.float32)


def test_parse_key_and_detect_c_major():
    sr = 44100
    t = np.arange(sr * 4) / sr
    chord = sum(
        0.05 * np.sin(2 * np.pi * librosa.midi_to_hz(midi) * t)
        for midi in (48, 52, 55, 60, 64, 67)
    ).astype(np.float32)
    key = detect_key(chord, sr, source="instrumental")
    assert key.mode == "major"
    assert key.tonic == 0
    assert parse_key("F# minor").name == "F♯ minor"


def test_pitch_polish_corrects_note_centers_and_writes_report(tmp_path):
    sr = 44100
    silence = np.zeros(int(sr * 0.12), dtype=np.float32)
    vocal = np.concatenate([
        sine_note(60, 0.8, cents=-42), silence,
        sine_note(62, 0.8, cents=38), silence,
        sine_note(64, 0.8, cents=-35),
    ])
    source = tmp_path / "vocal.wav"
    output = tmp_path / "polished.wav"
    report = tmp_path / "pitch.json"
    sf.write(source, vocal, sr)

    result = pitch_polish(
        str(source),
        str(output),
        style="studio",
        key_override="C major",
        report_path=str(report),
    )

    assert output.exists()
    assert report.exists()
    assert result["key"]["name"] == "C major"
    assert result["notes_detected"] >= 3
    assert result["notes_corrected"] >= 2
    data = json.loads(report.read_text("utf-8"))
    assert all("applied_cents" in edit for edit in data["edits"])
    rendered, rendered_sr = sf.read(output, always_2d=True)
    assert rendered_sr == sr
    assert len(rendered) == len(vocal)
    before_f0 = librosa.pyin(vocal[:int(sr * 0.75)], fmin=80, fmax=1000, sr=sr)[0]
    after_f0 = librosa.pyin(rendered[:int(sr * 0.75), 0], fmin=80, fmax=1000, sr=sr)[0]
    before_midi = float(np.nanmedian(librosa.hz_to_midi(before_f0)))
    after_midi = float(np.nanmedian(librosa.hz_to_midi(after_f0)))
    assert abs(after_midi - 60) < abs(before_midi - 60)
