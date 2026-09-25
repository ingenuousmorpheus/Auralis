"""My Voice full-song pipeline (AU-08): a rendered blueprint sung in a saved voice.

    blueprint melody guide + lyrics ──► guide score        (voice/guide.py)
    guide score ──────────────────────► dry guide vocal    (voice/singing_provider.py)
    guide vocal ──────────────────────► the chosen voice   (Seed-VC, existing provider)
    converted vocal ──────────────────► Pitch Polish       (existing, key from the blueprint)
    polished vocal + instrumental ────► Vocal Finish       (existing, placed against the beat)
    instrumental stems + vocal ───────► mix + master       (existing engine.pipeline)

The composer decides WHAT is sung, the guide singer HOW, Seed-VC WHO, and the
existing finish chain makes it record-ready (roadmap §9). ``convert`` is
injected so tests can run without the GPU provider; the API passes the real
Seed-VC call, guarded by the one-at-a-time engine lock.
"""
from __future__ import annotations

import json
import os

import numpy as np
import soundfile as sf

MAX_SINGLE_CALL = 6 * 60          # seconds; longer vocals are converted in chunks cut at rests
CHUNK_TARGET = 4 * 60


def _pitch_key(blueprint_key: str) -> str:
    """Blueprint key → the spelling ``voice.pitch.parse_key`` accepts."""
    from ..composer.chords import parse_key
    from .pitch import KEY_NAMES

    tonic, mode = parse_key(blueprint_key)
    return f"{KEY_NAMES[tonic]} {mode}"


def plan_chunks(spans: list[tuple[float, float]], total: float) -> list[tuple[float, float]]:
    """Cut points for conversion: whole vocal when short, else ≤ ~4 min pieces split in rests."""
    if not spans:
        return []
    start, end = max(0.0, spans[0][0] - 0.3), min(total, spans[-1][1] + 0.5)
    if end - start <= MAX_SINGLE_CALL:
        return [(start, end)]
    chunks, cur = [], start
    for (a, b), nxt in zip(spans, spans[1:] + [(None, None)]):
        if nxt[0] is not None and b - cur >= CHUNK_TARGET:
            cut = (b + nxt[0]) / 2                     # the middle of the rest
            chunks.append((cur, cut))
            cur = cut
    chunks.append((cur, end))
    return chunks


def sing_song(blueprint: dict, render: dict, profile, out_dir: str, convert, *, quality: str = "studio",
              seed: int = 0, pitch_style: str = "natural", finish_preset: str = "smooth-rnb",
              master: bool = True, progress=None) -> dict:
    """Run the full chain. ``render`` is an instrumental-render result (AU-05/06);
    ``convert(source, output, quality)`` converts one file into ``profile``'s voice."""
    from ..composer.arrange import arrange
    from .finish import finish_vocal
    from .guide import build_score, phrases
    from .pitch import pitch_polish
    from .singing_provider import get_singer

    def report(stage, pct):
        if progress:
            progress(stage, float(pct))

    os.makedirs(out_dir, exist_ok=True)
    seed = render.get("seed", seed) if render else seed
    report("writing the guide score", 2)
    arrangement = arrange(blueprint, seed=seed)                    # same seed → same melody as the render
    score = build_score(blueprint, arrangement["tracks"]["melody"])
    if not score:
        raise ValueError("This blueprint has no sung sections (every lead vocal is off).")
    total = float(render.get("duration_seconds") or blueprint["duration_seconds"] + 6) if render else \
        blueprint["duration_seconds"] + 6
    singer = get_singer("vocalise")
    report("singing the guide", 6)
    guide = singer.sing(score, total, seed=seed)
    guide_path = os.path.join(out_dir, "01_guide_vocal.wav")
    sf.write(guide_path, guide, 44100, subtype="PCM_24")
    with open(os.path.join(out_dir, "guide_score.json"), "w", encoding="utf-8") as f:
        json.dump([n.to_dict() for n in score], f, indent=1)

    # ── into the chosen voice ───────────────────────────────────────────
    spans = phrases(score)
    chunks = plan_chunks(spans, total)
    converted = np.zeros(len(guide), np.float32)
    for i, (a, b) in enumerate(chunks):
        report(f"converting to {profile.name} ({i + 1}/{len(chunks)})", 10 + 50 * i / len(chunks))
        s0, s1 = int(a * 44100), int(b * 44100)
        src = os.path.join(out_dir, f"chunk_{i:02d}_guide.wav")
        dst = os.path.join(out_dir, f"chunk_{i:02d}_voice.wav")
        sf.write(src, guide[s0:s1], 44100, subtype="PCM_16")
        convert(src, dst, quality)
        y, sr = sf.read(dst, always_2d=True, dtype="float32")
        y = y.mean(axis=1)
        if sr != 44100:
            from scipy.signal import resample_poly
            y = resample_poly(y, 44100, sr).astype(np.float32)
        n = min(len(y), s1 - s0, len(converted) - s0)
        converted[s0:s0 + n] = y[:n]
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass
    converted_path = os.path.join(out_dir, "02_my_voice.wav")
    sf.write(converted_path, converted, 44100, subtype="PCM_24")

    # ── existing polish chain ───────────────────────────────────────────
    instrumental = (render or {}).get("mix_path") or (render or {}).get("master_path")
    polished_path = os.path.join(out_dir, "03_pitch_polished.wav")
    report("pitch polish", 62)
    pitch_result = pitch_polish(converted_path, polished_path, style=pitch_style,
                                instrumental_path=None, key_override=_pitch_key(blueprint["key"]),
                                report_path=os.path.join(out_dir, "pitch_polish.json"),
                                progress=lambda s, p: report(f"pitch polish: {s}", 62 + p * 0.1))
    finished_path = os.path.join(out_dir, "04_finished_vocal.wav")
    preview_path = os.path.join(out_dir, "vocal_over_instrumental.wav") if instrumental else None
    report("vocal finish", 73)
    finish_result = finish_vocal(polished_path, finished_path, preset=finish_preset, intensity=0.7,
                                 instrumental_path=instrumental, preview_path=preview_path,
                                 report_path=os.path.join(out_dir, "vocal_finish.json"),
                                 progress=lambda s, p: report(f"vocal finish: {s}", 73 + p * 0.1))
    out = {
        "profile_id": profile.id, "profile_name": profile.name, "quality": quality, "seed": seed,
        "blueprint_id": blueprint.get("id"), "blueprint_revision": blueprint.get("revision"),
        "notes_sung": len(score), "syllables": sum(1 for n in score if n.syllable),
        "chunks": [[round(a, 2), round(b, 2)] for a, b in chunks],
        "guide_path": guide_path, "converted_path": converted_path, "polished_path": polished_path,
        "finished_path": finished_path, "preview_path": preview_path,
        "notes_corrected": pitch_result.get("notes_corrected"), "key": blueprint["key"],
        "song_mix_path": None, "song_master_path": None,
        "guide_sings_words": singer.sings_words,
    }

    # ── the song: instrumental stems + the finished vocal ───────────────
    stems = (render or {}).get("stems") or {}
    if master and stems:
        from ..engine.pipeline import run as run_pipeline
        from ..generation import MIX_OFFSETS, MIX_ROLES

        report("mixing the song", 84)
        paths = list(stems.values()) + [finished_path]
        roles = {p: MIX_ROLES.get(k, "other") for k, p in stems.items()}
        roles[finished_path] = "vocal"
        offsets = {p: MIX_OFFSETS[k] for k, p in stems.items() if k in MIX_OFFSETS}
        profile_id = (blueprint.get("arrangement") or {}).get("mix_profile") or "vocal-forward-rnb"
        mixed = run_pipeline(paths, os.path.join(out_dir, "song_master.wav"), profile_id=profile_id,
                             role_overrides=roles, gain_offsets=offsets,
                             progress=lambda s, p: report(f"song mix and master: {s}", 84 + p * 0.15))
        out.update(song_mix_path=mixed.mix_path, song_master_path=mixed.master_path,
                   report_path=mixed.report_path, mix_profile=profile_id,
                   after_lufs=mixed.master_result.get("after_lufs"),
                   after_peak_db=mixed.master_result.get("after_peak_db"))
    out["finish_preset"] = finish_preset
    out["vocal_to_music_db"] = (finish_result.get("analysis") or {}).get("vocal_to_instrument_db") \
        if isinstance(finish_result, dict) else None
    with open(os.path.join(out_dir, "song.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    report("done", 100)
    return out
