"""Reference vocal matching: guide timing/melody, source audio and identity.

Independent Auralis DSP, not a VocAlign host or a reconstruction of its code.
Uses bounded acoustic DTW and existing pitch tracking; renders only the take
through Pedalboard's formant-preserving offline time/pitch stretcher.
"""
from __future__ import annotations

from pathlib import Path
import json

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter

from .pitch import _track_pitch
from ..engine.loudness import apply_true_peak_ceiling

MAX_SECONDS = 180
MAX_BYTES = 100 * 1024 * 1024
TRACK_SR = 16000
MAX_PITCH_SHIFT = 12.0


def validate_audio(path, label='Vocal'):
    try:
        info = sf.info(path)
    except (RuntimeError, OSError):
        raise ValueError(f'{label}: this file is not readable WAV audio.') from None
    if info.format not in {'WAV', 'WAVEX', 'RF64'}:
        raise ValueError(f'{label}: please provide a WAV file.')
    if not 8000 <= info.samplerate <= 96000 or info.channels not in (1, 2):
        raise ValueError(f'{label}: use mono or stereo WAV at 8–96 kHz.')
    if not 0.5 <= info.duration <= MAX_SECONDS:
        raise ValueError(f'{label}: use a vocal between 0.5 and {MAX_SECONDS} seconds; split longer songs into sections.')
    if info.frames * info.channels > 18_000_000:
        raise ValueError(f'{label}: this WAV is too large; use 44.1 or 48 kHz audio or a shorter section.')
    return info


def _load(path, label):
    validate_audio(path, label)
    audio, sr = sf.read(path, always_2d=True, dtype='float32')
    if not np.all(np.isfinite(audio)):
        raise ValueError(f'{label}: audio contains invalid samples.')
    # Loudest channel avoids cancelling opposite-polarity stereo vocal copies.
    mono = audio[:, np.argmax(np.mean(audio ** 2, axis=0))]
    if np.max(np.abs(mono)) < 1e-5 or np.sqrt(np.mean(mono ** 2)) < 1e-6:
        raise ValueError(f'{label}: no audible vocal was found.')
    return audio, mono, sr


def _analysis(mono, sr):
    copy = librosa.resample(mono, orig_sr=sr, target_sr=TRACK_SR) if sr != TRACK_SR else mono.copy()
    _, bounds = librosa.effects.trim(copy, top_db=35, frame_length=1024, hop_length=256)
    start, end = bounds / TRACK_SR
    if end - start < 0.4:
        raise ValueError('Not enough vocal was found. Use isolated sung vocals with the same lyrics.')
    return copy[bounds[0]:bounds[1]], float(start), float(end)


def _features(audio, hop):
    mfcc = librosa.feature.mfcc(y=audio, sr=TRACK_SR, n_mfcc=13, n_fft=1024, hop_length=hop)[1:]
    # Cepstral normalization reduces a fixed difference in singer/recording colour.
    mfcc = (mfcc - np.mean(mfcc, axis=1, keepdims=True)) / np.maximum(np.std(mfcc, axis=1, keepdims=True), 5.0)
    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=hop)[0]
    energy = np.clip(np.log(np.maximum(rms, 1e-7) / max(float(np.max(rms)), 1e-7)), -5, 0)
    return np.vstack([mfcc * 0.25, energy[None, :] * 1.5]).astype(np.float32)


def _bounded_map(guide_audio, take_audio, guide_duration, take_duration):
    if not 0.5 <= take_duration / guide_duration <= 2.0:
        raise ValueError('The vocal lengths differ too much. Use the same song section and lyrics in both files.')
    # At most about 2,400 frames per axis; no full-song unbounded cost matrix.
    hop = max(256, int(np.ceil(max(len(guide_audio), len(take_audio)) / 2399 / 64)) * 64)
    guide, take = _features(guide_audio, hop), _features(take_audio, hop)
    accumulated, path = librosa.sequence.dtw(X=guide, Y=take, metric='euclidean',
        global_constraints=True, band_rad=0.25, weights_add=np.array([0.0, 0.35, 0.35]))
    score = float(accumulated[-1, -1] / len(path))
    indices = np.arange(guide.shape[1])
    mapped = np.array([np.median(path[path[:, 0] == index, 1]) for index in indices]) * hop / TRACK_SR
    target = indices * hop / TRACK_SR
    target[-1] = guide_duration
    mapped[0], mapped[-1] = 0, take_duration
    mapped = np.maximum.accumulate(mapped)
    return target, mapped, score


def _pitch(audio):
    times, f0, probability = _track_pitch(audio.astype(np.float32), TRACK_SR)
    valid = np.isfinite(f0) & (probability >= 0.45)
    midi = np.full(len(f0), np.nan)
    midi[valid] = librosa.hz_to_midi(f0[valid])
    if np.count_nonzero(valid) < 6:
        raise ValueError('A clear sung melody could not be detected. Use an isolated solo vocal, without backing music.')
    return times, midi


def _anchors(map_times, map_source, duration, source_duration, pitch_times, guide_pitch):
    controls = list(np.arange(0, duration, 0.25)) + [duration]
    # Add stable guide-note transitions, so blocks do not average different notes.
    stable = median_filter(np.nan_to_num(guide_pitch, nan=-999), size=5)
    for index in range(1, len(stable) - 4):
        if stable[index] > 0 and stable[index - 1] > 0 and abs(stable[index] - stable[index - 1]) > 0.65:
            point = float(pitch_times[index])
            if 0.08 < point < duration - 0.08:
                controls = [x for x in controls if x in (0, duration) or abs(x - point) >= 0.08]
                controls.append(point)
    target = np.array(sorted(set(controls)))
    if len(target) > 2 and target[-1] - target[-2] < 0.08:
        target = np.delete(target, -2)
    raw = np.interp(target, map_times, map_source)
    raw[0], raw[-1] = 0, source_duration
    dt = np.diff(target)
    slopes = np.maximum(np.diff(raw) / dt, 1e-5)
    # Keep every local stretch within 0.5–2x, retaining both endpoints.
    low, high = 0.0, 1e6
    for _ in range(70):
        factor = (low + high) / 2
        if np.sum(np.clip(slopes * factor, 0.5, 2.0) * dt) < source_duration:
            low = factor
        else:
            high = factor
    bounded = np.clip(slopes * ((low + high) / 2), 0.5, 2.0)
    source = np.r_[0.0, np.cumsum(bounded * dt)]
    source[-1] = source_duration
    return target, source, float(np.max(np.abs(source - raw)))


def _shifts(target, source, guide_times, guide_pitch, take_times, take_pitch, strength):
    shifts, uncertain, limited = [], 0, 0
    for start, end, a, b in zip(target[:-1], target[1:], source[:-1], source[1:]):
        selected = (take_times >= a) & (take_times < b) & np.isfinite(take_pitch)
        times = take_times[selected]
        if not len(times):
            shifts.append(0.0); uncertain += 1; continue
        mapped_times = start + (times - a) / max(b - a, 1e-8) * (end - start)
        guide_index = np.clip(np.searchsorted(guide_times, mapped_times), 0, len(guide_times) - 1)
        differences = guide_pitch[guide_index] - take_pitch[selected]
        differences = differences[np.isfinite(differences)]
        if len(differences) < 2:
            shifts.append(0.0); uncertain += 1; continue
        shift = float(np.median(differences)) * strength
        limited += abs(shift) > MAX_PITCH_SHIFT
        shifts.append(float(np.clip(shift, -MAX_PITCH_SHIFT, MAX_PITCH_SHIFT)))
    return shifts, uncertain, limited


def _render(take, sr, target, source, shifts, progress=None):
    from pedalboard import time_stretch
    length = int(round(target[-1] * sr))
    output = np.zeros((length, take.shape[1]), np.float32)
    norm = np.zeros(length, np.float32)
    for index, (a, b, s0, s1, shift) in enumerate(zip(target[:-1], target[1:], source[:-1], source[1:], shifts)):
        start, end = int(round(a * sr)), int(round(b * sr))
        speed = (s1 - s0) / (b - a)
        # Offline overlapping regions avoid realtime stretcher latency and hard cuts.
        pad = 0.035
        left = min(pad, a, s0 / speed)
        right = min(pad, target[-1] - b, (len(take) / sr - s1) / speed)
        source_start = max(0, int(round((s0 - left * speed) * sr)))
        source_end = min(len(take), int(round((s1 + right * speed) * sr)))
        left_samples, right_samples = int(round(left * sr)), max(0, int(round(right * sr)))
        out_start, out_end = start - left_samples, min(length, end + right_samples)
        expected = out_end - out_start
        segment = np.ascontiguousarray(take[source_start:source_end].T)
        rendered = time_stretch(segment, sr, stretch_factor=float(speed),
            pitch_shift_in_semitones=float(shift), preserve_formants=True, high_quality=True)
        rendered = np.asarray(rendered).reshape(take.shape[1], -1).T
        # Fixed scalar offline ratios produce the requested length within rounding.
        if abs(len(rendered) - expected) > max(256, int(sr * 0.02)):
            raise ValueError('The time stretcher could not preserve the alignment. Try a shorter vocal section.')
        rendered = librosa.util.fix_length(rendered, size=expected, axis=0)
        # Independent offline regions can arrive at different waveform phases.
        # Align their shared overlap within 4 ms before crossfading, preventing
        # destructive cancellation/dropouts on sustained vowels.
        overlap = np.flatnonzero(norm[out_start:out_end] > 0)
        if len(overlap) > 64:
            lo, hi = int(overlap[0]), int(overlap[-1]) + 1
            reference = np.mean(output[out_start + lo:out_start + hi] /
                norm[out_start + lo:out_start + hi, None], axis=1)
            incoming = np.mean(rendered, axis=1)
            best, lag = -1.0, 0
            for offset in range(-int(sr * .004), int(sr * .004) + 1):
                left, right = lo - offset, hi - offset
                if left < 0 or right > len(incoming):
                    continue
                candidate = incoming[left:right]
                denominator = np.linalg.norm(reference) * np.linalg.norm(candidate)
                similarity = float(np.dot(reference, candidate) / denominator) if denominator > 1e-10 else 0
                if similarity > best:
                    best, lag = similarity, offset
            if best > .5 and lag:
                rendered = np.roll(rendered, lag, axis=0)
                if lag > 0:
                    rendered[:lag] = 0
                else:
                    rendered[lag:] = 0
        envelope = np.ones(expected, np.float32)
        if left_samples:
            envelope[:left_samples] = np.linspace(0, 1, left_samples)
        tail = out_end - end
        if tail:
            envelope[-tail:] = np.linspace(1, 0, tail)
        output[out_start:out_end] += rendered * envelope[:, None]
        norm[out_start:out_end] += envelope
        if progress:
            progress('matching your timing and melody', 40 + 50 * (index + 1) / len(shifts))
    return output / np.maximum(norm[:, None], 1e-8)


def match_vocal(guide_path, take_path, output_path, report_path=None, strength=1.0, progress=None):
    """Same lyrics/order, isolated monophonic singers. Originals are never written.

    Output follows the guide timeline at the take sample rate/channel count.
    Pitch targets the guide register (no octave folding), capped at ±12 semitones.
    """
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('Melody strength must be between 0 and 1.')
    sources = {Path(guide_path).resolve(), Path(take_path).resolve()}
    destinations = [Path(output_path).resolve()] + ([Path(report_path).resolve()] if report_path else [])
    if any(p in sources for p in destinations) or len(set(destinations)) != len(destinations):
        raise ValueError('Output and report must use new paths, separate from the originals.')
    if any(p.exists() for p in destinations):
        raise ValueError('Output already exists. Choose a new output path.')
    if progress: progress('reading the two vocals', 5)
    guide, guide_mono, guide_sr = _load(guide_path, 'Demo vocal')
    take, take_mono, sr = _load(take_path, 'Your vocal')
    ref_audio, ref_start, ref_end = _analysis(guide_mono, guide_sr)
    src_audio, src_start, src_end = _analysis(take_mono, sr)
    if progress: progress('finding matching phrases', 12)
    mt, ms, cost = _bounded_map(ref_audio, src_audio, ref_end - ref_start, src_end - src_start)
    if progress: progress('reading the demo melody and your notes', 25)
    gt, gp = _pitch(ref_audio)
    st, sp = _pitch(src_audio)
    target, source, adjustment = _anchors(mt, ms, ref_end - ref_start, src_end - src_start, gt, gp)
    shifts, uncertain, limited = _shifts(target, source, gt, gp, st, sp, strength)
    cropped = take[int(round(src_start * sr)):int(round(src_end * sr))]
    aligned = _render(cropped, sr, target, source, shifts, progress)
    length = int(round(len(guide) / guide_sr * sr))
    output = np.zeros((length, take.shape[1]), np.float32)
    start = int(round(ref_start * sr))
    available = min(len(aligned), length - start)
    output[start:start + available] = aligned[:available]
    if not np.all(np.isfinite(output)):
        raise ValueError('Matching produced invalid samples; no result was saved.')
    output = apply_true_peak_ceiling(output, sr, -1.0)
    warnings = ['Experimental acoustic matching: audition consonants, breaths and note transitions. Same lyrics/order and isolated solo vocals are required.']
    if adjustment > 0.12:
        warnings.append('Some timing moves were reduced to keep stretching within 0.5–2x. Check those phrases.')
    if uncertain:
        warnings.append(f'{uncertain} regions lacked reliable paired pitch; their pitch was left unchanged.')
    if limited:
        warnings.append(f'{limited} regions exceeded the one-octave correction limit. Their melody match is partial.')
    if cost > 2.0:
        warnings.append('The acoustic match is weak. Check that both files contain the same words in the same order.')
    report = {'engine': 'auralis-reference-match-v1', 'plugin_used': False, 'mode': 'timing-and-melody',
        'duration_seconds': round(length / sr, 3), 'sample_rate': sr, 'channels': take.shape[1],
        'melody_strength': strength, 'regions': len(shifts), 'pitch_regions_changed': sum(abs(s) >= 0.08 for s in shifts),
        'uncertain_pitch_regions': uncertain, 'limited_pitch_regions': int(limited), 'alignment_cost': round(cost, 3),
        'warnings': warnings, 'anchors': [{'demo_seconds': round(float(a + ref_start), 4),
            'take_seconds': round(float(b + src_start), 4)} for a, b in zip(target, source)],
        'output_path': str(output_path)}
    sf.write(output_path, output, sr, subtype='PCM_24')
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    if progress: progress('done', 100)
    return report
