"""Audio generation behind a provider boundary (AU-05+).

``render_instrumental`` runs the whole structured path:
blueprint → ``composer.arrange`` → MIDI → provider stems → the existing
``engine.pipeline`` mix and master. Providers are looked up by id, so richer
renderers can be added without touching the composer or the mixer.
"""
from __future__ import annotations

import json
import os

from .base import RenderProvider, RenderResult
from .synth import SynthRenderer

PROVIDERS: dict[str, RenderProvider] = {"synth": SynthRenderer()}
# Stem → mixer role, so the pipeline never has to guess (no detection needed).
MIX_ROLES = {"drums": "drums", "bass": "bass", "keys": "harmonic", "pad": "harmonic", "fx": "other",
             "atmosphere": "other"}
# Stems that should sit below their role target (dB): the atmosphere is a bed.
MIX_OFFSETS = {"atmosphere": -6.0, "fx": -2.0}


def get_provider(provider_id: str = "synth") -> RenderProvider:
    if provider_id not in PROVIDERS:
        raise KeyError(f"Unknown render provider: {provider_id}")
    return PROVIDERS[provider_id]


def list_providers() -> list[dict]:
    return [p.status() for p in PROVIDERS.values()]


def render_instrumental(blueprint: dict, out_dir: str, seed: int = 0, provider: str = "synth",
                        master: bool = True, progress=None) -> dict:
    """Render a blueprint to stems, a MIDI file and (when ``master``) a mixed and
    mastered instrumental. Returns paths and a summary."""
    from ..composer.arrange import arrange
    from ..composer.midi import write_midi
    from ..composer.validation import validate_blueprint

    def report(stage, pct):
        if progress:
            progress(stage, float(pct))

    check = validate_blueprint(blueprint)
    if not check["ok"]:
        raise ValueError("The blueprint has errors: " + " ".join(check["errors"]))
    os.makedirs(out_dir, exist_ok=True)
    report("arranging parts", 3)
    arrangement = arrange(blueprint, seed=seed)
    report("planning atmosphere", 5)
    from .atmosphere import plan_atmosphere

    atmos_plan = plan_atmosphere(blueprint)
    arrangement["atmosphere_plan"] = atmos_plan
    arrangement["tracks"]["atmosphere"] = _atmosphere_notes(atmos_plan)
    midi_path = os.path.join(out_dir, "arrangement.mid")
    write_midi(arrangement, midi_path)
    bp_path = os.path.join(out_dir, "blueprint.json")
    with open(bp_path, "w", encoding="utf-8") as f:
        json.dump(blueprint, f, indent=2, ensure_ascii=False)

    renderer = get_provider(provider)
    result: RenderResult = renderer.render(
        arrangement, os.path.join(out_dir, "stems"), seed=seed,
        progress=lambda stage, pct: report(stage, 8 + pct * 0.42))

    out = {
        "provider": result.provider, "seed": seed, "tempo": arrangement["tempo"], "key": arrangement["key"],
        "duration_seconds": result.duration_seconds, "note_counts": arrangement["counts"],
        "stems": result.stems, "melody_guide_path": result.extras.get("melody"),
        "atmosphere": {"counts": atmos_plan["counts"], "levels": atmos_plan["levels"],
                       "layers": [{k: l[k] for k in ("kind", "section", "why")} for l in atmos_plan["layers"]]},
        "midi_path": midi_path, "blueprint_path": bp_path, "blueprint_id": blueprint.get("id"),
        "blueprint_revision": blueprint.get("revision"), "profile_id": None,
        "mix_path": None, "master_path": None,
    }
    if master and result.stems:
        from ..engine.pipeline import run as run_pipeline

        profile = (blueprint.get("arrangement") or {}).get("mix_profile") or "neutral"
        paths = list(result.stems.values())
        roles = {path: MIX_ROLES[part] for part, path in result.stems.items()}
        offsets = {path: MIX_OFFSETS[part] for part, path in result.stems.items() if part in MIX_OFFSETS}
        mixed = run_pipeline(paths, os.path.join(out_dir, "instrumental_master.wav"), profile_id=profile,
                             role_overrides=roles, gain_offsets=offsets,
                             progress=lambda stage, pct: report(f"mix and master: {stage}", 52 + pct * 0.46))
        out.update(profile_id=profile, mix_path=mixed.mix_path, master_path=mixed.master_path,
                   report_path=mixed.report_path, session_path=mixed.session_path,
                   after_lufs=mixed.master_result.get("after_lufs"),
                   after_peak_db=mixed.master_result.get("after_peak_db"))
    with open(os.path.join(out_dir, "render.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in out.items()}, f, indent=2)
    report("done", 100)
    return out


def _atmosphere_notes(plan: dict) -> list:
    """Pitched atmosphere layers as MIDI notes, so a DAW gets them too."""
    notes = []
    for l in plan["layers"]:
        if l["kind"] in ("bed", "swell", "tail") or not l["pitches"]:
            continue
        vel = int(40 + 60 * min(1.0, l["gain"]))
        if l["kind"] == "sparkle":
            b = 0.0
            while b < l["beats"] - 1e-6:
                p = l["pitches"][int(b * 2) % len(l["pitches"])]
                notes.append((l["start"] + b, 0.45, p, vel))
                b += 0.5
        else:
            for p in l["pitches"]:
                notes.append((l["start"], l["beats"], p, vel))
    return sorted(notes)


__all__ = ["MIX_ROLES", "PROVIDERS", "RenderProvider", "RenderResult", "get_provider", "list_providers",
           "render_instrumental"]
