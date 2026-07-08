"""Alignment and validation for AI-guide / real-singer calibration pairs."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def ingest_paired_calibration(
    guide_path: str,
    singer_path: str,
    profile_dir: str | Path,
    name: str = "paired calibration",
) -> dict:
    """Align two matching performances and save high-confidence phrase pairs."""
    guide, guide_sr = _load_mono(guide_path)
    singer, singer_sr = _load_mono(singer_path)
    analysis_sr = 22050
    hop = 2048
    guide_chroma = _chroma(guide, guide_sr, analysis_sr, hop)
    singer_chroma = _chroma(singer, singer_sr, analysis_sr, hop)
    distance, path = librosa.sequence.dtw(
        X=guide_chroma,
        Y=singer_chroma,
        metric="euclidean",
        subseq=True,
        backtrack=True,
        step_sizes_sigma=np.array([[1, 1], [1, 2], [2, 1]]),
        weights_mul=np.array([1.0, 1.5, 1.5]),
    )
    path = path[::-1]
    frame_seconds = hop / analysis_sr
    target_span = (path[-1, 1] - path[0, 1] + 1) * frame_seconds
    source_span = len(guide_chroma.T) * frame_seconds
    timing_slope = target_span / max(source_span, 1e-9)
    similarities = np.array([
        _cosine(guide_chroma[:, source_i], singer_chroma[:, target_i])
        for source_i, target_i in path
    ])
    median_similarity = float(np.median(similarities))
    if not 0.82 <= timing_slope <= 1.18 or median_similarity < 0.68:
        raise ValueError(
            "The guide and singer recordings do not appear to be the same performance "
            f"(timing slope {timing_slope:.2f}, melodic similarity {median_similarity:.2f})."
        )

    pair_id = uuid.uuid4().hex[:12]
    pair_dir = Path(profile_dir) / "paired" / pair_id
    pair_dir.mkdir(parents=True, exist_ok=False)
    clips = []
    window_frames = max(1, round(12.0 / frame_seconds))
    step_frames = window_frames
    for source_start in range(0, guide_chroma.shape[1], step_frames):
        source_stop = min(source_start + window_frames, guide_chroma.shape[1])
        mask = (path[:, 0] >= source_start) & (path[:, 0] < source_stop)
        local = path[mask]
        if len(local) < window_frames * 0.55:
            continue
        local_similarity = float(np.median([
            _cosine(guide_chroma[:, i], singer_chroma[:, j]) for i, j in local
        ]))
        local_slope = (local[-1, 1] - local[0, 1] + 1) / max(source_stop - source_start, 1)
        if local_similarity < 0.74 or not 0.86 <= local_slope <= 1.14:
            continue
        source_seconds = (
            source_start * frame_seconds,
            source_stop * frame_seconds,
        )
        target_seconds = (
            local[0, 1] * frame_seconds,
            (local[-1, 1] + 1) * frame_seconds,
        )
        index = len(clips) + 1
        guide_out = pair_dir / f"guide_{index:03d}.wav"
        singer_out = pair_dir / f"singer_{index:03d}.wav"
        sf.write(
            guide_out,
            guide[int(source_seconds[0] * guide_sr):int(source_seconds[1] * guide_sr)],
            guide_sr,
            subtype="PCM_24",
        )
        sf.write(
            singer_out,
            singer[int(target_seconds[0] * singer_sr):int(target_seconds[1] * singer_sr)],
            singer_sr,
            subtype="PCM_24",
        )
        clips.append({
            "guide_path": str(guide_out),
            "singer_path": str(singer_out),
            "guide_seconds": [round(v, 3) for v in source_seconds],
            "singer_seconds": [round(v, 3) for v in target_seconds],
            "melodic_similarity": round(local_similarity, 4),
            "timing_slope": round(float(local_slope), 4),
        })

    if not clips:
        raise ValueError("The performances align globally, but no clean phrase pairs passed validation.")
    report = {
        "id": pair_id,
        "name": name[:80],
        "guide_source": Path(guide_path).name,
        "singer_source": Path(singer_path).name,
        "median_melodic_similarity": round(median_similarity, 4),
        "timing_slope": round(float(timing_slope), 4),
        "normalized_alignment_cost": round(
            float(distance[-1, path[-1, 1]] / max(len(path), 1)), 4
        ),
        "clip_count": len(clips),
        "usable_singer_seconds": float(round(sum(
            clip["singer_seconds"][1] - clip["singer_seconds"][0] for clip in clips
        ), 2)),
        "clips": clips,
    }
    (pair_dir / "calibration.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, always_2d=True, dtype="float32")
    return np.mean(audio, axis=1).astype(np.float32), sr


def _chroma(audio, sr, target_sr, hop):
    if sr != target_sr:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
    return librosa.feature.chroma_cqt(y=audio, sr=target_sr, hop_length=hop)


def _cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
