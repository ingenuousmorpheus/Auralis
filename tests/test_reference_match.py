"""Behavioural tests: rendered timing/melody, source identity and upload safety."""
import io
import time
from pathlib import Path

import librosa
import numpy as np
import pytest
import soundfile as sf

from auralis.voice.reference_match import match_vocal, validate_audio, _anchors

SR = 16000


def note(midi, duration, colour=0.0):
    t = np.arange(round(SR * duration)) / SR
    hz = librosa.midi_to_hz(midi)
    env = np.minimum(t / .03, 1) * np.minimum((duration - t) / .03, 1)
    return (.15 * (np.sin(2 * np.pi * hz * t) + colour * np.sin(4 * np.pi * hz * t)) * env).astype(np.float32)


def phrase(notes, durations, lead=.2, gaps=(.15, .1), colour=0):
    parts = [np.zeros(round(SR * lead))]
    for index, (midi, duration) in enumerate(zip(notes, durations)):
        parts.append(note(midi, duration, colour))
        parts.append(np.zeros(round(SR * (gaps[index] if index < len(gaps) else .2))))
    return np.concatenate(parts).astype(np.float32)


@pytest.fixture
def pair(tmp_path):
    guide = phrase([60, 64, 62], [.6, .8, .6])
    take = phrase([58, 62, 60], [.9, .55, .75], lead=.4, gaps=(.15, .2), colour=.35)
    guide_path, take_path = tmp_path / 'demo.wav', tmp_path / 'mine.wav'
    sf.write(guide_path, guide, SR)
    sf.write(take_path, take, SR)
    return guide_path, take_path


def pitch_center(audio, start, end, sr=SR):
    f0 = librosa.yin(audio[round(start * sr):round(end * sr)], fmin=80, fmax=800, sr=sr)
    return float(np.nanmedian(librosa.hz_to_midi(f0)))


def onsets(audio):
    # Independent 10 ms RMS detector, not DTW or the matcher's feature map.
    block = SR // 100
    energy = np.array([np.sqrt(np.mean(audio[i:i + block] ** 2)) for i in range(0, len(audio), block)])
    active = energy > max(energy) * .18
    return np.flatnonzero(active & ~np.r_[False, active[:-1]]) / 100


def test_render_matches_timing_and_melody_without_copying_demo(pair, tmp_path):
    guide, take = pair
    originals = [p.read_bytes() for p in pair]
    destination, report_path = tmp_path / 'matched.wav', tmp_path / 'report.json'
    report = match_vocal(guide, take, destination, report_path)
    output, sr = sf.read(destination)
    demo, _ = sf.read(guide)
    original, _ = sf.read(take)
    assert sr == SR and len(output) == len(demo)
    assert np.all(np.isfinite(output))
    assert np.max(np.abs(output)) <= 10 ** (-1 / 20) + .001
    assert [p.read_bytes() for p in pair] == originals
    # Each sung note is corrected toward the corresponding guide note, not just a key.
    for start, end, expected in [(.32, .68, 60), (1.08, 1.55, 64), (1.98, 2.3, 62)]:
        assert abs(pitch_center(output, start, end) - expected) < .35
    before, after, target = onsets(original), onsets(output), onsets(demo)
    assert len(after) == len(target) == 3
    assert np.mean(np.abs(after - target)) < .09
    assert np.mean(np.abs(after - target)) < np.mean(np.abs(before - target)) * .4
    # Demo has no second harmonic; take does. Its colour remains in the output.
    def harmonic_ratio(audio):
        segment = audio[round(.35 * SR):round(.65 * SR)]
        spectrum = abs(np.fft.rfft(segment * np.hanning(len(segment))))
        frequencies = np.fft.rfftfreq(len(segment), 1 / SR)
        hz = librosa.midi_to_hz(60)
        return max(spectrum[abs(frequencies - 2 * hz) < 12]) / max(spectrum[abs(frequencies - hz) < 12])
    assert harmonic_ratio(output) > harmonic_ratio(demo) + .03
    assert report['plugin_used'] is False
    assert report['pitch_regions_changed'] > 0 and report_path.is_file()


def test_zero_melody_strength_keeps_take_pitch(pair, tmp_path):
    match_vocal(*pair, tmp_path / 'timing.wav', strength=0)
    output, _ = sf.read(tmp_path / 'timing.wav')
    assert abs(pitch_center(output, .32, .68) - 58) < .35


def test_stereo_and_different_sample_rate(pair, tmp_path):
    guide, take = pair
    audio, _ = sf.read(take)
    stereo = np.stack([audio, audio * .5], axis=1)
    sf.write(take, stereo, SR)
    demo, _ = sf.read(guide)
    sf.write(guide, librosa.resample(demo, orig_sr=SR, target_sr=22050), 22050)
    report = match_vocal(guide, take, tmp_path / 'stereo.wav')
    output, sr = sf.read(tmp_path / 'stereo.wav', always_2d=True)
    assert output.shape[1] == 2 and sr == SR
    assert report['channels'] == 2
    assert np.sqrt(np.mean(output[:, 1] ** 2)) / np.sqrt(np.mean(output[:, 0] ** 2)) == pytest.approx(.5, abs=.05)


@pytest.mark.parametrize('value', [-.1, 1.1, float('nan')])
def test_bad_strength(pair, tmp_path, value):
    with pytest.raises(ValueError, match='strength'):
        match_vocal(*pair, tmp_path / 'output.wav', strength=value)


def test_protect_sources_and_existing_outputs(pair, tmp_path):
    guide, take = pair
    for destination in [guide, take]:
        with pytest.raises(ValueError, match='originals'):
            match_vocal(guide, take, destination)
    existing = tmp_path / 'existing.wav'
    existing.write_bytes(b'keep me')
    with pytest.raises(ValueError, match='exists'):
        match_vocal(guide, take, existing)
    assert existing.read_bytes() == b'keep me'


def test_silence_and_invalid_audio(pair, tmp_path):
    silent = tmp_path / 'silent.wav'
    sf.write(silent, np.zeros(SR), SR)
    with pytest.raises(ValueError, match='audible'):
        match_vocal(pair[0], silent, tmp_path / 'result.wav')
    broken = tmp_path / 'bad.wav'
    broken.write_bytes(b'not audio')
    with pytest.raises(ValueError, match='readable WAV'):
        validate_audio(broken)
    assert not (tmp_path / 'result.wav').exists()


def test_extreme_durations_rejected(pair, tmp_path):
    short = tmp_path / 'short.wav'
    sf.write(short, note(60, .6), SR)
    with pytest.raises(ValueError, match='lengths differ'):
        match_vocal(pair[0], short, tmp_path / 'result.wav')


def test_map_has_monotonic_bounded_rates():
    target, source, _ = _anchors(np.array([0, .5, 1, 1.5, 2]), np.array([0, 0, .1, 1.9, 2]),
        2, 2, np.arange(20) / 10, np.ones(20) * 60)
    rates = np.diff(source) / np.diff(target)
    assert min(rates) >= .5 - 1e-8 and max(rates) <= 2 + 1e-8
    assert source[-1] == 2 and np.all(np.diff(source) > 0)


def test_api_real_matching_download_and_validation(pair, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from auralis.api import main
    from auralis.api import reference_match as api
    monkeypatch.setattr(main, 'WORK_ROOT', str(tmp_path / 'jobs'))
    monkeypatch.setattr(main, 'JOBS', {})
    # Real DSP is used by this round trip.
    with TestClient(main.app) as client:
        response = client.post('/voice/match', files={
            'guide': ('demo.wav', pair[0].read_bytes(), 'audio/wav'),
            'take': ('mine.wav', pair[1].read_bytes(), 'audio/wav')})
        assert response.status_code == 200
        job_id = response.json()['job_id']
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            job = client.get('/jobs/' + job_id).json()
            if job['stage'] in ('done', 'error'):
                break
            time.sleep(.1)
        assert job['stage'] == 'done', job
        assert client.get(f'/voice/match/{job_id}/report').status_code == 200
        for kind in ['guide', 'take', 'result']:
            audio = client.get(f'/voice/match/{job_id}/audio/{kind}')
            assert audio.status_code == 200
            assert sf.info(io.BytesIO(audio.content)).format == 'WAV'
        assert client.get(f'/voice/match/{job_id}/audio/other').status_code == 404
        assert client.get('/voice/match/missing/audio/result').status_code == 404
        count = len(main.JOBS)
        assert client.post('/voice/match', files={'guide': ('bad.exe', b'x'), 'take': ('mine.wav', b'x')}).status_code == 415
        assert client.post('/voice/match', files={'guide': ('bad.wav', b'x'), 'take': ('mine.wav', b'x')}).status_code == 422
        assert len(main.JOBS) == count
        monkeypatch.setattr(api, 'MAX_BYTES', 10)
        assert client.post('/voice/match', files={'guide': ('demo.wav', pair[0].read_bytes()), 'take': ('mine.wav', pair[1].read_bytes())}).status_code == 413
        assert len(main.JOBS) == count
        assert api._busy.acquire(blocking=False)
        try:
            assert client.post('/voice/match', files={'guide': ('demo.wav', b'x'), 'take': ('mine.wav', b'x')}).status_code == 409
        finally:
            api._busy.release()

def test_worker_failure_releases_busy_gate(tmp_path, monkeypatch):
    from auralis.api import main
    from auralis.api import reference_match as api
    job = {'work': str(tmp_path), 'kind': 'vocal-match', 'stage': 'queued', 'result': None, 'error': None}
    monkeypatch.setattr(main, 'JOBS', {'failed': job})
    def fail(*args, **kwargs):
        raise ValueError('A clear sung melody could not be detected.')
    monkeypatch.setattr(api, 'match_vocal', fail)
    assert api._busy.acquire(blocking=False)
    api._run('failed', 'guide.wav', 'take.wav', 1.0)
    assert job['stage'] == 'error' and 'melody' in job['error']
    assert job['result'] is None
    assert api._busy.acquire(blocking=False)
    api._busy.release()
