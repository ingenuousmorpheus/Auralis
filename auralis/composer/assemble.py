"""Automatic song assembly (AU-10): one prompt → a finished song in a project, stems kept.

    prompt + lyrics ──► blueprint          (composer.build_blueprint)
    blueprint ────────► instrumental       (generation.render_instrumental: stems, MIDI, master)
    blueprint + voice ► vocals             (voice.full_song.sing_song: lead, doubles, harmonies, ad-libs)
    everything ───────► a new project      (blueprint.json, lyrics.txt, every stem tagged with its mix role)

and back again: ``remix_project`` rebuilds the song from the project's own
stems with per-stem level, mute and solo, through the unchanged mix/master
pipeline, and saves the result as a new master. Work therefore no longer only
flows job → project: songs can be re-made *from* project assets (AU-01 gap).
"""
from __future__ import annotations

import os

# asset "part" → mixer role; the backing bus and atmosphere/FX keep their offsets
MIX_ROLE = {"drums": "drums", "bass": "bass", "keys": "harmonic", "pad": "harmonic", "fx": "other", "generated": "harmonic",
            "atmosphere": "other", "lead_vocal": "vocal", "backing_vocals": "other"}
DEFAULT_OFFSET = {"atmosphere": -6.0, "fx": -2.0, "backing_vocals": 4.0}


def save_song_to_project(store, name: str, blueprint: dict, render: dict, song: dict | None) -> dict:
    """Create a project holding the whole song, with mix roles on every stem."""
    project = store.create(name)
    pid = project.id
    store.save_blueprint(pid, blueprint)
    added = []

    def add(path, kind, part, label, extra=None):
        if path and os.path.isfile(path):
            meta = {"part": part, "mix_role": MIX_ROLE.get(part), "blueprint_id": blueprint.get("id")}
            meta.update(extra or {})
            a = store.add_asset(pid, path, kind, name=label, origin={"type": "song-assembly"},
                                metadata={k: v for k, v in meta.items() if v is not None})
            added.append(a)

    for part, path in (render.get("stems") or {}).items():
        add(path, "stem", part, f"{part}.wav")
    add(render.get("midi_path"), "generated", "midi", "arrangement.mid")
    add(render.get("melody_guide_path"), "generated", "melody_guide", "melody_guide.wav")
    if song:
        add(song.get("finished_path"), "vocal", "lead_vocal", "lead_vocal.wav",
            {"voice": song.get("profile_name")})
        add(song.get("backing_path"), "vocal", "backing_vocals", "backing_vocals.wav",
            {"voice": song.get("profile_name")})
        for part, path in (song.get("backing_stems") or {}).items():
            add(path, "vocal", f"bv_{part}", f"bv_{part}.wav")           # individual parts, not in the remix
        add(song.get("guide_path"), "generated", "guide_vocal", "guide_vocal.wav")
        add(song.get("song_mix_path"), "mix", "song_mix", "song_pre_master.wav")
        add(song.get("song_master_path"), "master", "song_master", "song.wav",
            {"after_lufs": song.get("after_lufs")})
    else:
        add(render.get("mix_path"), "mix", "instrumental_mix", "instrumental_pre_master.wav")
        add(render.get("master_path"), "master", "instrumental_master", "instrumental.wav",
            {"after_lufs": render.get("after_lufs")})
    return {"project_id": pid, "assets": len(added)}


def remix_stems(store, project_id: str) -> list:
    """The project's mixable stems (assets carrying a mix role), newest per part."""
    project = store.get(project_id)
    latest = {}
    for a in project.assets:
        part = (a.metadata or {}).get("part")
        if (a.metadata or {}).get("mix_role") and part:
            latest[part] = a                                      # later assets replace earlier ones
    return list(latest.values())


def backing_parts(store, project_id: str) -> list:
    """The individual backing-vocal parts saved with a sung song (bv_* assets, newest per part)."""
    latest = {}
    for a in store.get(project_id).assets:
        part = (a.metadata or {}).get("part", "")
        if part.startswith("bv_"):
            latest[part] = a
    return list(latest.values())


def rebalance_backing(store, project_id: str, levels: dict, out_dir: str) -> dict:
    """Rebuild the backing-vocal bus from the saved parts with new levels ({part: dB},
    part names without the bv_ prefix) and save it as the newest backing_vocals stem.
    No re-singing: the parts are already converted, shaped and panned."""
    import numpy as np
    import soundfile as sf

    parts = backing_parts(store, project_id)
    if not parts:
        raise ValueError("This song has no separate backing-vocal parts to rebalance.")
    tracks, sr = [], 44100
    for a in parts:
        y, sr = sf.read(str(store.asset_path(project_id, a.id)), always_2d=True, dtype="float32")
        db = float(levels.get(a.metadata["part"][3:], 0.0))
        tracks.append(y * (0.0 if db <= -60 else 10 ** (min(12.0, db) / 20)))      # -60 dB or less = muted
    bus = np.zeros((max(len(t) for t in tracks), max(t.shape[1] for t in tracks)), np.float32)
    for t in tracks:
        bus[: len(t), : t.shape[1]] += t
    peak = float(np.abs(bus).max()) or 1.0
    if peak > 0.89:
        bus *= 0.89 / peak
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "backing_vocals_rebalanced.wav")
    sf.write(path, bus, sr, subtype="PCM_24")
    n = sum(1 for a in store.get(project_id).assets if (a.metadata or {}).get("part") == "backing_vocals")
    asset = store.add_asset(project_id, path, "vocal", name=f"backing_vocals_{n + 1:02d}.wav",
                            origin={"type": "rebalance"},
                            metadata={"part": "backing_vocals", "mix_role": "other",
                                      "levels": ", ".join(f"{k} {v:+g} dB" for k, v in sorted(levels.items()))})
    return {"asset_id": asset.id, "name": asset.name}


def remix_project(store, project_id: str, levels: dict | None, out_dir: str, profile_id: str | None = None,
                  progress=None, backing_levels: dict | None = None) -> dict:
    """Re-mix and re-master from the project's own stems.

    ``levels``: {asset_id: {"gain_db": float, "mute": bool, "solo": bool}}.
    Solo wins over mute; unmentioned stems play at their default level.
    """
    from ..engine.pipeline import run as run_pipeline

    levels = levels or {}
    rebalanced = None
    if backing_levels:
        rebalanced = rebalance_backing(store, project_id, backing_levels, os.path.join(out_dir, "backing"))
    stems = remix_stems(store, project_id)
    if not stems:
        raise ValueError("This project has no mixable stems (make or save a song first).")
    soloed = {aid for aid, v in levels.items() if v.get("solo")}
    paths, roles, offsets, used = [], {}, {}, []
    for a in stems:
        cfg = levels.get(a.id, {})
        if soloed and a.id not in soloed:
            continue
        if not soloed and cfg.get("mute"):
            continue
        path = str(store.asset_path(project_id, a.id))
        paths.append(path)
        roles[path] = a.metadata["mix_role"]
        offset = DEFAULT_OFFSET.get(a.metadata.get("part"), 0.0) + float(cfg.get("gain_db", 0.0))
        if offset:
            offsets[path] = max(-30.0, min(12.0, offset))
        used.append({"asset_id": a.id, "part": a.metadata.get("part"), "gain_db": float(cfg.get("gain_db", 0.0))})
    if not paths:
        raise ValueError("Everything is muted.")
    if profile_id is None:
        bp = store.blueprint(project_id) or {}
        profile_id = (bp.get("arrangement") or {}).get("mix_profile") or "vocal-forward-rnb"
    os.makedirs(out_dir, exist_ok=True)
    mixed = run_pipeline(paths, os.path.join(out_dir, "remix_master.wav"), profile_id=profile_id,
                         role_overrides=roles, gain_offsets=offsets, progress=progress)
    n = sum(1 for a in store.get(project_id).assets if (a.metadata or {}).get("part") == "remix_master") + 1
    master = store.add_asset(project_id, mixed.master_path, "master", name=f"remix_{n:02d}.wav",
                             origin={"type": "remix"},
                             metadata={"part": "remix_master", "after_lufs": mixed.master_result.get("after_lufs"),
                                       "stems_used": len(used), "profile_id": profile_id})
    return {"master_asset_id": master.id, "name": master.name, "stems": used, "profile_id": profile_id,
            "backing_rebalanced": rebalanced,
            "after_lufs": mixed.master_result.get("after_lufs"),
            "after_peak_db": mixed.master_result.get("after_peak_db")}
