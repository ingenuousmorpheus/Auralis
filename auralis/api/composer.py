"""Song Blueprint endpoints (AU-04): create, revise, regenerate a section, save to a project.

Blueprints are computed locally from the prompt, Artist DNA, the R&B Theory
Atlas and the trained voice range. Nothing is uploaded and no audio is made.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..composer import build_blueprint, regenerate, revise
from ..composer.chords import ChordError

router = APIRouter(tags=["composer"])


class BlueprintRequest(BaseModel):
    prompt: str = ""
    lyrics: str = ""
    era: str | None = None
    harmony: str | None = None
    vocal: str | None = None
    groove: str | None = None
    key: str | None = None
    tempo: float | None = Field(None, ge=40, le=220)
    length_seconds: int | None = Field(None, ge=30, le=720)
    use_dna: bool = True
    use_voice: bool = True
    voice_profile_id: str | None = None
    artist_dna_weight: float = Field(0.5, ge=0, le=1)
    seed: int = 0


class ReviseRequest(BaseModel):
    blueprint: dict
    changes: dict


class RegenerateRequest(BaseModel):
    blueprint: dict
    section_id: str


class SaveRequest(BaseModel):
    blueprint: dict


def _voice(profile_id: str | None):
    from ..voice import VoiceProfileStore

    store = VoiceProfileStore()
    try:
        if profile_id:
            return store.get(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    profiles = store.list()
    return next((p for p in profiles if p.training_status == "trained"), None) or \
        (profiles[0] if profiles else None)


def _catalog() -> list[dict]:
    """Tempo / key / form of each switched-on song, for the originality check."""
    from .artist import LIBRARY

    out = []
    for s in LIBRARY.songs():
        if s.included and s.analysis_status == "done" and s.summary:
            out.append({"bpm": s.summary.get("bpm"), "key": s.summary.get("key"),
                        "form": s.summary.get("roles_form")})
    return out


@router.post("/composer/blueprint")
def create_blueprint(req: BlueprintRequest):
    """A complete, explained blueprint for the prompt (not saved until you save it)."""
    dna, voice = None, None
    if req.use_dna:
        from .artist import artist_dna

        dna = artist_dna(req.voice_profile_id)
    if req.use_voice:
        voice = _voice(req.voice_profile_id)
    voice_range = (voice.pitch_low_midi, voice.pitch_high_midi) if voice else None
    settings = {k: getattr(req, k) for k in ("era", "harmony", "vocal", "groove", "key", "tempo",
                                             "length_seconds")}
    try:
        return build_blueprint(req.prompt, req.lyrics, dna=dna, voice_range=voice_range,
                               voice_name=voice.name if voice else None,
                               catalog=_catalog() if req.use_dna else None,
                               artist_dna_weight=req.artist_dna_weight, seed=req.seed, **settings)
    except ChordError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, f"Unknown option: {exc}") from exc


@router.post("/composer/blueprint/revise")
def revise_blueprint(req: ReviseRequest):
    """Apply edits (tempo, key, title, lyrics, sections) and re-derive chords,
    timings, energy, vocal registers and checks. Invalid edits return 422."""
    try:
        bp = revise(req.blueprint, req.changes, catalog=_catalog())
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"Could not apply that edit: {exc}") from exc
    if not bp["validation"]["ok"]:
        raise HTTPException(422, " ".join(bp["validation"]["errors"]))
    return bp


@router.post("/composer/blueprint/regenerate")
def regenerate_section(req: RegenerateRequest):
    """New chords for one section type (all its sections), keeping everything else."""
    try:
        return regenerate(req.blueprint, req.section_id, catalog=_catalog())
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _projects():
    from .projects import PROJECT_STORE

    return PROJECT_STORE


@router.put("/projects/{project_id}/blueprint")
def save_blueprint(project_id: str, req: SaveRequest):
    bp = req.blueprint
    if not (bp.get("validation") or {}).get("ok", False):
        raise HTTPException(422, "Fix the blueprint's errors before saving.")
    try:
        return _projects().save_blueprint(project_id, bp)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/projects/{project_id}/blueprint")
def get_blueprint(project_id: str):
    try:
        bp = _projects().blueprint(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if bp is None:
        raise HTTPException(404, "This project has no blueprint yet.")
    return bp


@router.get("/projects/{project_id}/blueprint/revisions")
def list_revisions(project_id: str):
    try:
        return _projects().blueprint_revisions(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


# ── AU-05: render the blueprint to an instrumental ─────────────────────────

class RenderRequest(BaseModel):
    blueprint: dict
    seed: int = 0
    provider: str = "synth"
    master: bool = True


RENDER_FILES = {"master": "master_path", "mix": "mix_path", "melody_guide": "melody_guide_path",
                "midi": "midi_path", "report": "report_path"}


def _run_render(job_id: str, blueprint: dict, seed: int, provider: str, master: bool):
    import os

    from ..generation import render_instrumental
    from .main import JOBS

    job = JOBS[job_id]
    try:
        result = render_instrumental(blueprint, os.path.join(job["work"], "render"), seed=seed,
                                     provider=provider, master=master,
                                     progress=lambda stage, pct: job.update(stage=stage, pct=pct))
        job["result"] = result
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@router.get("/composer/providers")
def providers():
    from ..generation import list_providers

    return list_providers()


@router.post("/composer/render")
async def render(req: RenderRequest):
    """Blueprint → arrangement → MIDI → local instruments → stems → mix + master.
    One render at a time (memory). Progress via /jobs/{id}."""
    import asyncio

    from ..composer.validation import validate_blueprint
    from ..generation import PROVIDERS
    from .main import JOBS, _create_job

    if req.provider not in PROVIDERS:
        raise HTTPException(404, f"Unknown render provider: {req.provider}")
    if not validate_blueprint(req.blueprint)["ok"]:
        raise HTTPException(422, "Fix the blueprint's errors before rendering.")
    if any(j.get("kind") == "instrumental-render" and j.get("stage") not in ("done", "error")
           for j in JOBS.values()):
        raise HTTPException(409, "An instrumental is already rendering.")
    job_id = _create_job()
    JOBS[job_id].update(kind="instrumental-render", stage="queued", pct=0.0,
                        blueprint_title=req.blueprint.get("title"))
    asyncio.create_task(asyncio.to_thread(_run_render, job_id, req.blueprint, req.seed, req.provider, req.master))
    return {"job_id": job_id, "status": "started"}


@router.get("/composer/render/{job_id}/file/{name}")
def render_file(job_id: str, name: str):
    import os

    from fastapi.responses import FileResponse

    from .main import JOBS

    job = JOBS.get(job_id)
    if not job or job.get("kind") != "instrumental-render" or not job.get("result"):
        raise HTTPException(404, "No finished render with that id.")
    result = job["result"]
    path = result["stems"].get(name) if name in result["stems"] else result.get(RENDER_FILES.get(name, ""))
    if not path or not os.path.isfile(path):
        raise HTTPException(404, f"No '{name}' in this render.")
    media = {".wav": "audio/wav", ".mid": "audio/midi", ".md": "text/markdown"}.get(os.path.splitext(path)[1],
                                                                                   "application/octet-stream")
    filename = {"master": "instrumental.wav", "midi": "arrangement.mid"}.get(name, os.path.basename(path))
    return FileResponse(path, media_type=media, filename=filename)
