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
