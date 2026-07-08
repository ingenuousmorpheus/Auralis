"""Analysis-driven post-production for converted singing vocals."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

from ..engine.loudness import apply_true_peak_ceiling, measure


@dataclass
class VocalFinishAnalysis:
    integrated_lufs: float
    true_peak_db: float
    crest_factor_db: float
    dynamic_range_db: float
    mud_ratio: float
    presence_ratio: float
    sibilance_ratio: float
    low_rumble_ratio: float
    instrumental_lufs: float | None = None
    vocal_to_instrument_db: float | None = None
    masking_score: float | None = None


@dataclass
class VocalFinishDecision:
    preset: str
    intensity: float
    highpass_hz: float
    mud_cut_db: float
    presence_db: float
    air_db: float
    deess_db: float
    leveling_ratio: float
    leveling_threshold_db: float
    peak_ratio: float
    peak_threshold_db: float
    saturation_drive_db: float
    ambience_mix: float
    double_mix: float
    output_gain_db: float
    reasons: list[str]


# Rack modules the GUI can override. Each maps a module id to the decision
# fields it owns, with safe (min, max) clamps for user-supplied values.
MODULE_PARAMS = {
    "eq": {
        "highpass_hz": (20.0, 250.0),
        "mud_cut_db": (-8.0, 0.0),
        "presence_db": (-4.0, 6.0),
        "air_db": (-4.0, 6.0),
    },
    "deess": {"deess_db": (-10.0, 0.0)},
    "compressor": {
        "leveling_threshold_db": (-32.0, -6.0),
        "leveling_ratio": (1.0, 6.0),
        "peak_threshold_db": (-26.0, -2.0),
        "peak_ratio": (1.0, 10.0),
    },
    "saturation": {"saturation_drive_db": (0.0, 6.0)},
    "dimension": {"double_mix": (0.0, 0.4)},
    "space": {"ambience_mix": (0.0, 0.4)},
    "output": {"output_gain_db": (-8.0, 8.0)},
}

# Values that make a module audibly transparent when its power button is off.
MODULE_BYPASS = {
    "eq": {"highpass_hz": 20.0, "mud_cut_db": 0.0, "presence_db": 0.0, "air_db": 0.0},
    "deess": {"deess_db": 0.0},
    "compressor": {"leveling_ratio": 1.0, "peak_ratio": 1.0},
    "saturation": {"saturation_drive_db": 0.0},
    "dimension": {"double_mix": 0.0},
    "space": {"ambience_mix": 0.0},
    "output": {"output_gain_db": 0.0},
}


def apply_module_overrides(
    decision: VocalFinishDecision,
    modules: dict | None,
) -> VocalFinishDecision:
    """Apply GUI rack state (per-module bypass + knob values) onto a decision.

    ``modules`` looks like ``{"eq": {"enabled": true, "presence_db": 1.5}, ...}``.
    Unknown modules and parameters are ignored; values are clamped to the
    ranges in MODULE_PARAMS so the API cannot be driven into unstable settings.
    """
    if not modules:
        return decision
    touched = []
    for module_id, state in modules.items():
        params = MODULE_PARAMS.get(module_id)
        if params is None or not isinstance(state, dict):
            continue
        if state.get("enabled") is False:
            for field, neutral in MODULE_BYPASS[module_id].items():
                setattr(decision, field, neutral)
            touched.append(f"{module_id} bypassed")
            continue
        for field, (lo, hi) in params.items():
            if field in state:
                try:
                    value = float(state[field])
                except (TypeError, ValueError):
                    continue
                setattr(decision, field, round(float(np.clip(value, lo, hi)), 3))
                touched.append(module_id)
    if touched:
        decision.reasons.append(
            "Manual rack settings were applied on top of the analysis: "
            + ", ".join(sorted(set(touched))) + "."
        )
    return decision


PRESETS = {
    "natural": {
        "presence": 0.3, "air": 0.3, "saturation": 0.2,
        "ambience": 0.04, "double": 0.0, "target_over_beat": -2.0,
    },
    "polished-pop": {
        "presence": 1.2, "air": 1.4, "saturation": 0.8,
        "ambience": 0.10, "double": 0.10, "target_over_beat": -1.0,
    },
    "smooth-rnb": {
        "presence": 0.6, "air": 0.8, "saturation": 0.6,
        "ambience": 0.16, "double": 0.06, "target_over_beat": -1.8,
    },
    "intimate": {
        "presence": 0.8, "air": 0.5, "saturation": 0.4,
        "ambience": 0.05, "double": 0.0, "target_over_beat": -2.4,
    },
    "forward": {
        "presence": 1.5, "air": 1.0, "saturation": 1.0,
        "ambience": 0.07, "double": 0.08, "target_over_beat": -0.3,
    },
}


def finish_vocal(
    vocal_path: str,
    output_path: str,
    preset: str = "polished-pop",
    intensity: float = 0.75,
    instrumental_path: str | None = None,
    preview_path: str | None = None,
    report_path: str | None = None,
    modules: dict | None = None,
    progress=None,
) -> dict:
    """Analyze and finish a converted vocal, optionally in instrumental context."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown Vocal Finish preset: {preset}")
    intensity = float(np.clip(intensity, 0.0, 1.0))
    vocal, sr = sf.read(vocal_path, always_2d=True, dtype="float32")
    vocal = _mono(vocal)
    instrumental = None
    instrumental_sr = None
    if instrumental_path:
        instrumental, instrumental_sr = sf.read(
            instrumental_path, always_2d=True, dtype="float32"
        )
        if instrumental_sr != sr:
            instrumental = _resample(instrumental, instrumental_sr, sr)
    if progress:
        progress("analyzing vocal and context", 15)

    analysis = analyze_vocal(vocal, sr, instrumental)
    decision = decide_finish(analysis, preset, intensity)
    decision = apply_module_overrides(decision, modules)
    if progress:
        progress("cleaning tone and sibilance", 35)
    processed = _process(vocal, sr, decision)
    processed = apply_true_peak_ceiling(processed, sr, -1.0)
    sf.write(output_path, processed, sr, subtype="PCM_24")

    preview_written = None
    if instrumental is not None and preview_path:
        if progress:
            progress("placing vocal inside the instrumental", 75)
        preview = _context_mix(processed, instrumental, sr, decision)
        preview = apply_true_peak_ceiling(preview, sr, -1.0)
        sf.write(preview_path, preview, sr, subtype="PCM_24")
        preview_written = preview_path

    report = {
        "analysis": asdict(analysis),
        "decision": asdict(decision),
        "output_path": output_path,
        "preview_path": preview_written,
    }
    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    if progress:
        progress("vocal finish complete", 98)
    report["report_path"] = report_path
    return report


def analyze_vocal(
    vocal: np.ndarray,
    sr: int,
    instrumental: np.ndarray | None = None,
) -> VocalFinishAnalysis:
    mono = _mono(vocal)[:, 0]
    stats = measure(mono[:, np.newaxis], sr)
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(mono)))
    crest = 20 * np.log10(max(peak, 1e-9) / max(rms, 1e-9))
    frame_rms = _frame_rms(mono, sr)
    active = frame_rms[frame_rms > 10 ** (-55 / 20)]
    if active.size:
        dynamic = 20 * np.log10(
            max(float(np.percentile(active, 95)), 1e-9)
            / max(float(np.percentile(active, 20)), 1e-9)
        )
    else:
        dynamic = 0.0
    freqs, power = _spectrum(mono, sr)
    total = float(np.sum(power)) + 1e-12
    ratio = lambda lo, hi: float(np.sum(power[(freqs >= lo) & (freqs < hi)]) / total)
    mud = ratio(160, 420)
    presence = ratio(1800, 5000)
    sibilance = ratio(5200, 10500)
    rumble = ratio(20, 75)

    inst_lufs = None
    v_to_i = None
    masking = None
    if instrumental is not None:
        inst = _stereo(instrumental)
        inst_stats = measure(inst, sr)
        inst_lufs = float(inst_stats.integrated_lufs)
        v_to_i = float(stats.integrated_lufs - inst_lufs)
        inst_mono = np.mean(inst, axis=1)
        length = min(len(inst_mono), len(mono))
        vf, vp = _spectrum(mono[:length], sr)
        _, ip = _spectrum(inst_mono[:length], sr)
        band = (vf >= 180) & (vf <= 10000)
        vn = vp[band] / (np.sum(vp[band]) + 1e-12)
        inn = ip[band] / (np.sum(ip[band]) + 1e-12)
        masking = float(np.sum(np.minimum(vn, inn)))

    return VocalFinishAnalysis(
        integrated_lufs=round(stats.integrated_lufs, 2),
        true_peak_db=round(stats.true_peak_db, 2),
        crest_factor_db=round(crest, 2),
        dynamic_range_db=round(dynamic, 2),
        mud_ratio=round(mud, 4),
        presence_ratio=round(presence, 4),
        sibilance_ratio=round(sibilance, 4),
        low_rumble_ratio=round(rumble, 4),
        instrumental_lufs=round(inst_lufs, 2) if inst_lufs is not None else None,
        vocal_to_instrument_db=round(v_to_i, 2) if v_to_i is not None else None,
        masking_score=round(masking, 4) if masking is not None else None,
    )


def decide_finish(
    analysis: VocalFinishAnalysis,
    preset: str,
    intensity: float,
) -> VocalFinishDecision:
    style = PRESETS[preset]
    reasons = []
    highpass = 65.0
    if analysis.low_rumble_ratio > 0.012:
        highpass = 85.0
        reasons.append("Sub-rumble was elevated, so the cleanup filter moved higher.")
    mud_cut = -min(max((analysis.mud_ratio - 0.16) * 18.0, 0.0), 3.0) * intensity
    if mud_cut < -0.4:
        reasons.append("Low-mid buildup was reduced to keep the vocal out of the beat.")
    presence = style["presence"] * intensity
    if analysis.presence_ratio < 0.10:
        presence += 0.5 * intensity
        reasons.append("Presence energy was low, so intelligibility was gently restored.")
    air = style["air"] * intensity
    deess = -min(max((analysis.sibilance_ratio - 0.075) * 35.0, 0.0), 5.0) * intensity
    if deess < -0.5:
        reasons.append("Sibilance was above the comfortable range and was dynamically softened.")

    # Two gentle stages: slow leveling, then faster peak control.
    dynamic_need = float(np.clip((analysis.dynamic_range_db - 8.0) / 10.0, 0.0, 1.0))
    level_ratio = 1.35 + 0.9 * intensity + 0.5 * dynamic_need
    peak_ratio = 1.8 + 1.7 * intensity
    level_threshold = float(np.clip(analysis.integrated_lufs + 3.0, -28.0, -12.0))
    peak_threshold = float(np.clip(level_threshold + 5.0, -20.0, -6.0))
    reasons.append("Two light compression stages provide leveling and peak control without one stage pumping.")

    output_gain = 0.0
    if analysis.vocal_to_instrument_db is not None:
        target = style["target_over_beat"]
        output_gain = float(np.clip(target - analysis.vocal_to_instrument_db, -4.0, 4.0))
        reasons.append("Output level was set from the vocal-to-instrument relationship.")
        if (analysis.masking_score or 0) > 0.72:
            mud_cut -= 0.5 * intensity
            presence += 0.4 * intensity
            reasons.append("High spectral overlap triggered a little more pocket and presence.")
    else:
        reasons.append("No instrumental was supplied, so level was optimized in solo rather than mix context.")

    return VocalFinishDecision(
        preset=preset,
        intensity=round(intensity, 3),
        highpass_hz=highpass,
        mud_cut_db=round(mud_cut, 2),
        presence_db=round(presence, 2),
        air_db=round(air, 2),
        deess_db=round(deess, 2),
        leveling_ratio=round(level_ratio, 2),
        leveling_threshold_db=round(level_threshold, 2),
        peak_ratio=round(peak_ratio, 2),
        peak_threshold_db=round(peak_threshold, 2),
        saturation_drive_db=round(style["saturation"] * intensity, 2),
        ambience_mix=round(style["ambience"] * intensity, 3),
        double_mix=round(style["double"] * intensity, 3),
        output_gain_db=round(output_gain, 2),
        reasons=reasons,
    )


def _process(vocal: np.ndarray, sr: int, d: VocalFinishDecision) -> np.ndarray:
    x = _mono(vocal).astype(np.float32)
    # pedalboard is a hard dependency; if the chain fails the render must fail
    # loudly rather than silently shipping an unprocessed vocal as "finished".
    from pedalboard import (
        Compressor,
        Gain,
        HighShelfFilter,
        HighpassFilter,
        PeakFilter,
        Pedalboard,
    )
    cleanup = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=d.highpass_hz),
        PeakFilter(cutoff_frequency_hz=280.0, gain_db=d.mud_cut_db, q=0.9),
        PeakFilter(cutoff_frequency_hz=3200.0, gain_db=d.presence_db, q=0.8),
        HighShelfFilter(cutoff_frequency_hz=9000.0, gain_db=d.air_db, q=0.7),
    ])
    x = cleanup(x.T, sr).T.astype(np.float32)
    x = _deess(x, sr, d.deess_db)
    serial = Pedalboard([
        Compressor(
            threshold_db=d.leveling_threshold_db,
            ratio=d.leveling_ratio,
            attack_ms=28.0,
            release_ms=160.0,
        ),
        Compressor(
            threshold_db=d.peak_threshold_db,
            ratio=d.peak_ratio,
            attack_ms=4.0,
            release_ms=65.0,
        ),
        Gain(gain_db=d.output_gain_db),
    ])
    x = serial(x.T, sr).T.astype(np.float32)

    if d.saturation_drive_db > 0:
        drive = 10 ** (d.saturation_drive_db / 20.0)
        x = np.tanh(x * drive) / np.tanh(np.float32(drive))
    dry = x.copy()
    x = _stereo(dry)
    if d.double_mix > 0:
        x += _double_send(dry, sr, d.double_mix)
    if d.ambience_mix > 0:
        x += _ambience_send(dry, sr, d.ambience_mix)
    return x.astype(np.float32)


def _deess(audio: np.ndarray, sr: int, reduction_db: float) -> np.ndarray:
    if reduction_db >= -0.05:
        return audio
    mono = audio[:, 0]
    sos = butter(4, [5200, min(10500, sr * 0.45)], btype="bandpass", fs=sr, output="sos")
    sib = sosfilt(sos, mono).astype(np.float32)
    frame = max(1, int(sr * 0.008))
    env = np.sqrt(np.convolve(sib * sib, np.ones(frame) / frame, mode="same"))
    threshold = float(np.percentile(env, 72))
    control = np.clip((env - threshold) / max(threshold, 1e-9), 0.0, 1.0)
    max_reduction = 1.0 - 10 ** (reduction_db / 20.0)
    out = mono - sib * control.astype(np.float32) * np.float32(max_reduction)
    return out[:, np.newaxis].astype(np.float32)


def _double_send(audio: np.ndarray, sr: int, mix: float) -> np.ndarray:
    mono = audio[:, 0]
    left_delay, right_delay = int(sr * 0.014), int(sr * 0.021)
    left = np.pad(mono, (left_delay, 0))[:len(mono)]
    right = np.pad(mono, (right_delay, 0))[:len(mono)]
    return np.stack([left * mix, right * mix], axis=1).astype(np.float32)


def _ambience_send(audio: np.ndarray, sr: int, mix: float) -> np.ndarray:
    stereo = _stereo(audio)
    wet = np.zeros_like(stereo)
    for delay_ms, gain, cross in ((42, 0.55, False), (71, 0.35, True), (113, 0.22, False)):
        delay = int(sr * delay_ms / 1000)
        delayed = np.pad(stereo, ((delay, 0), (0, 0)))[:len(stereo)]
        if cross:
            delayed = delayed[:, ::-1]
        wet += delayed * np.float32(gain)
    return (wet * np.float32(mix)).astype(np.float32)


def _context_mix(
    vocal: np.ndarray,
    instrumental: np.ndarray,
    sr: int,
    decision: VocalFinishDecision,
) -> np.ndarray:
    beat = _stereo(instrumental)
    voice = _stereo(vocal)
    length = max(len(beat), len(voice))
    beat = np.pad(beat, ((0, length - len(beat)), (0, 0)))
    voice = np.pad(voice, ((0, length - len(voice)), (0, 0)))
    # Small center pocket in the beat, proportional to the analysis decision.
    mid = 0.5 * (beat[:, 0] + beat[:, 1])
    side = 0.5 * (beat[:, 0] - beat[:, 1])
    pocket_db = min(abs(decision.mud_cut_db) * 0.35 + decision.presence_db * 0.15, 1.2)
    mid *= np.float32(10 ** (-pocket_db / 20.0))
    beat[:, 0], beat[:, 1] = mid + side, mid - side
    return (beat + voice).astype(np.float32)


def _spectrum(audio: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    n_fft = 4096
    if len(audio) < n_fft:
        audio = np.pad(audio, (0, n_fft - len(audio)))
    frames = min(len(audio), sr * 30)
    window = np.hanning(frames)
    spec = np.fft.rfft(audio[:frames] * window)
    return np.fft.rfftfreq(frames, 1 / sr), np.abs(spec) ** 2


def _frame_rms(audio: np.ndarray, sr: int) -> np.ndarray:
    frame, hop = max(1, int(sr * 0.05)), max(1, int(sr * 0.025))
    return np.array([
        np.sqrt(np.mean(audio[i:i + frame].astype(np.float64) ** 2))
        for i in range(0, max(1, len(audio) - frame + 1), hop)
    ])


def _mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio[:, np.newaxis]
    return np.mean(audio, axis=1, keepdims=True)


def _stereo(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return np.stack([audio, audio], axis=1)
    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)
    return audio[:, :2]


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    from math import gcd
    from scipy.signal import resample_poly

    common = gcd(orig_sr, target_sr)
    return resample_poly(
        audio, target_sr // common, orig_sr // common, axis=0
    ).astype(np.float32)
