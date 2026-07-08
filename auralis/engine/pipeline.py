"""Full mixing pipeline.

Orchestrates:
  1. Analysis   — per-stem feature extraction + role detection
  2. Mixing     — heuristic MixParams generation (Path A)
                  (Path B Diff-MST controller hooks in here when weights land)
  3. Console    — apply params via pedalboard DSP, sum to stereo
  4. Mastering  — chain straight into Phase 1 mastering pipeline

Input:  list of stem file paths + optional reference path + style profile id
Output: MixPipelineResult with the mastered stereo file + full provenance
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass

import numpy as np
import soundfile as sf

from .analysis import analyse, StemAnalysis
from .console import apply_and_sum, ConsoleResult
from .mastering import master_file, MasterResult
from .mixer import mix, MixParams
from .profiles_loader import load_profile


@dataclass
class MixPipelineResult:
    # Paths
    mix_path: str            # pre-master stereo bounce
    master_path: str         # final mastered file
    # Provenance
    stem_analyses: list[dict]
    mix_params: list[dict]
    master_result: dict
    profile_id: str
    mode: str                # "heuristic" | "diff-mst" (future)
    reference_used: bool
    session_path: str
    report_path: str


def run(
    stem_paths: list[str],
    output_path: str,
    profile_id: str = "neutral",
    reference_path: str | None = None,
    role_overrides: dict[str, str] | None = None,   # {path: role}
    target_lufs: float | None = None,
    progress=None,
) -> MixPipelineResult:
    """Run the full mix + master pipeline.

    ``role_overrides`` maps a stem path to a manually-set role, bypassing
    auto-detection for that stem.
    """
    def report(stage: str, pct: float) -> None:
        if progress:
            progress(stage, pct)

    overrides = role_overrides or {}
    profile = load_profile(profile_id)
    work = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(work, exist_ok=True)

    # ── 1. Analysis ────────────────────────────────────────────────────────
    report("analysing stems", 5)
    analyses: list[StemAnalysis] = []
    audios: list[tuple[np.ndarray, int]] = []

    for path in stem_paths:
        audio, sr = sf.read(path, always_2d=True, dtype="float32")
        role_override = overrides.get(path)
        a = analyse(audio, sr, path=path, role=role_override)
        analyses.append(a)
        audios.append((audio, sr))

    # ── 2. Mixing (heuristic, Path A) ──────────────────────────────────────
    report("computing mix parameters", 20)
    mode = "heuristic"
    params: list[MixParams] = mix(analyses, profile_id=profile_id)

    # ── 3. DSP console ────────────────────────────────────────────────────
    mix_path = os.path.join(work, "pre_master.wav")

    def console_progress(stage: str, pct: float) -> None:
        report(stage, 30 + int(pct * 0.4))   # 30–70%

    console_result: ConsoleResult = apply_and_sum(
        audios, params, mix_path, progress=console_progress
    )

    # ── 4. Mastering ──────────────────────────────────────────────────────
    report("mastering", 72)

    def master_progress(stage: str, pct: float) -> None:
        report(f"mastering: {stage}", 72 + int(pct * 0.26))   # 72–98%

    master_result: MasterResult = master_file(
        mix_path, output_path, profile,
        target_lufs=target_lufs,
        reference_path=reference_path,
        progress=master_progress,
    )

    report("done", 100)

    session_path = os.path.join(work, "session.json")
    report_path = os.path.join(work, "report.md")
    analyses_dict = [_analysis_to_dict(a) for a in analyses]
    params_dict = [p.to_dict() for p in params]
    master_dict = master_result.__dict__
    session = {
        "profile_id": profile_id,
        "mode": mode,
        "reference_used": reference_path is not None,
        "stem_analyses": analyses_dict,
        "mix_params": params_dict,
        "master_result": master_dict,
    }
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(_build_report(session))

    return MixPipelineResult(
        mix_path=mix_path,
        master_path=output_path,
        stem_analyses=analyses_dict,
        mix_params=params_dict,
        master_result=master_dict,
        profile_id=profile_id,
        mode=mode,
        reference_used=reference_path is not None,
        session_path=session_path,
        report_path=report_path,
    )


def _analysis_to_dict(a: StemAnalysis) -> dict:
    return {
        "path": a.path,
        "role": a.role,
        "role_confidence": a.role_confidence,
        "integrated_lufs": a.integrated_lufs,
        "spectral_centroid_hz": a.spectral_centroid_hz,
        "onset_rate_hz": a.onset_rate_hz,
        "low_energy_ratio": a.low_energy_ratio,
    }


def _build_report(session: dict) -> str:
    lines = [
        "# Auralis mix report",
        "",
        f"- Profile: `{session['profile_id']}`",
        f"- Engine mode: `{session['mode']}`",
        f"- Reference used: `{session['reference_used']}`",
        "",
        "## Stem decisions",
        "",
        "| Stem | Role | Gain | Pan | High-pass | EQ moves |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for analysis, params in zip(session["stem_analyses"], session["mix_params"]):
        stem = os.path.basename(analysis["path"])
        eq = ", ".join(
            f"{b['gain_db']:+.1f} dB @ {b['freq']:.0f} Hz"
            for b in params["eq_bands"]
        ) or "none"
        lines.append(
            f"| {stem} | {analysis['role']} | {params['gain_db']:+.1f} dB | "
            f"{params['pan']:+.2f} | {params['highpass_hz']:.0f} Hz | {eq} |"
        )
    master = session["master_result"]
    lines.extend([
        "",
        "## Master",
        "",
        f"- Loudness: {master['before_lufs']:.1f} → {master['after_lufs']:.1f} LUFS",
        f"- True peak: {master['before_peak_db']:.2f} → {master['after_peak_db']:.2f} dBTP",
        f"- Mode: `{master['mode']}`",
        "",
    ])
    return "\n".join(lines)
