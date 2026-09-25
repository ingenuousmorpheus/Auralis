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
    influence: str = "all"                   # all | closest | picked (AU-12 retrieval)
    influence_song_ids: list[str] = []


class ReviseRequest(BaseModel):
    blueprint: dict
    changes: dict


class RegenerateRequest(BaseModel):
    blueprint: dict
    section_id: str


class SaveRequest(BaseModel):
    blueprint: dict


def _voice(profile_id: str | None):
    from .main import VOICE_STORE as store       # the app's shared store

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
            a = LIBRARY.analysis(s.id) or {}
            out.append({"song_id": s.id, "title": s.title, "bpm": s.summary.get("bpm"),
                        "key": s.summary.get("key"), "form": s.summary.get("roles_form"),
                        "roman_per_bar": (a.get("harmony") or {}).get("roman_per_bar")})
    return out


def _focused(req, voice):
    """Retrieval (AU-12): DNA from the closest (or picked) songs instead of the whole catalog."""
    from ..artist.dna import build_dna
    from ..artist.retrieval import focused_dna, retrieve
    from ..composer.brief import parse_brief
    from .artist import LIBRARY

    songs = LIBRARY.songs()
    analyses = {s.id: LIBRARY.analysis(s.id) for s in songs if s.analysis_status == "done"}
    brief = parse_brief(req.prompt, req.lyrics, key=req.key, tempo=req.tempo)
    whole = build_dna(songs, analyses).get("traits", {})          # fills what the prompt doesn't say
    target = {"bpm": brief["tempo"] or (whole.get("tempo") or {}).get("median"),
              "mode": brief["mode"] or ("minor" if (whole.get("key") or {}).get("minor_share", 0) >= 0.5 else None),
              "syncopation": (whole.get("groove") or {}).get("syncopation"),
              "chorus_lift": (whole.get("form") or {}).get("chorus_lift"),
              "family": None if not brief["key"] else
              (brief["key"]["tonic"] if brief["key"]["mode"] == "major" else (brief["key"]["tonic"] + 3) % 12)}
    picked = req.influence_song_ids if req.influence == "picked" else []
    ranked = retrieve(target, songs, analyses, n=max(3, len(picked)) if picked else 5, picked=picked)
    if picked:
        ranked = [r for r in ranked if r["song_id"] in picked] or ranked
    dna = focused_dna([r["song_id"] for r in ranked], songs, analyses, voice)
    return dna, ranked


@router.post("/composer/blueprint")
def create_blueprint(req: BlueprintRequest):
    """A complete, explained blueprint for the prompt (not saved until you save it)."""
    dna, voice, influences = None, None, None
    if req.use_voice:
        voice = _voice(req.voice_profile_id)
    if req.use_dna:
        from .artist import artist_dna

        if req.influence in ("closest", "picked"):
            dna, influences = _focused(req, voice)
        else:
            dna = artist_dna(req.voice_profile_id)
    voice_range = (voice.pitch_low_midi, voice.pitch_high_midi) if voice else None
    settings = {k: getattr(req, k) for k in ("era", "harmony", "vocal", "groove", "key", "tempo",
                                             "length_seconds")}
    try:
        bp = build_blueprint(req.prompt, req.lyrics, dna=dna, voice_range=voice_range,
                             voice_name=voice.name if voice else None,
                             catalog=_catalog() if req.use_dna else None,
                             artist_dna_weight=req.artist_dna_weight, seed=req.seed, **settings)
        if influences:
            bp["inputs"]["influences"] = influences
            bp["why"]["influence"] = [f"Artist DNA focused on {len(influences)} of your songs: " + "; ".join(
                f"“{i['title']}” ({', '.join(i['reasons'])})" for i in influences) + "."]
        return bp
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


# ── AU-07/08: sing the song in a saved voice ───────────────────────────────

class SingRequest(BaseModel):
    blueprint: dict
    render_job_id: str | None = None
    profile_id: str
    quality: str = "studio"
    master: bool = True
    production: str = "full"            # lead | doubles | harmony | full (capped per section by the blueprint)


SING_FILES = {"song": "song_master_path", "song_mix": "song_mix_path", "vocal": "finished_path",
              "polished": "polished_path", "converted": "converted_path", "guide": "guide_path",
              "preview": "preview_path", "report": "report_path", "backing": "backing_path"}
BACKING_PARTS = ("double_l", "double_r", "harmony_high", "harmony_low", "adlibs")


def _run_sing(job_id: str, req: SingRequest, render: dict | None):
    import os

    from ..voice.full_song import sing_song
    from .main import JOBS, VOICE_PROVIDER, VOICE_STORE
    from .voices import ENGINE_LOCK

    job = JOBS[job_id]
    try:
        profile = VOICE_STORE.get(req.profile_id)

        def convert(src, dst, quality):
            job.update(stage=f"waiting for the voice engine ({profile.name})")
            with ENGINE_LOCK:
                job.update(stage=f"converting to {profile.name} (voice engine running; a full song takes minutes)")
                result = VOICE_PROVIDER.convert(
                    source_path=src, reference_path=profile.reference_path, output_path=dst,
                    semitone_shift=0, quality=quality, checkpoint_path=profile.checkpoint_path,
                    config_path=profile.config_path)
            if result.get("output_path") and result["output_path"] != dst and os.path.isfile(result["output_path"]):
                import shutil
                shutil.copyfile(result["output_path"], dst)

        result = sing_song(req.blueprint, render, profile, os.path.join(job["work"], "song"), convert,
                           quality=req.quality, master=req.master, production=req.production,
                           progress=lambda stage, pct: job.update(stage=stage, pct=pct))
        job["result"] = result
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        message = str(exc)
        if "1455" in message or "paging file" in message.lower():
            message += " (Windows ran out of memory for the voice engine: close large apps and try again.)"
        job.update(stage="error", error=message)


@router.post("/composer/sing")
async def sing(req: SingRequest):
    """Guide singer → the chosen voice → Pitch Polish → Vocal Finish → song mix and master.
    Uses the instrumental from ``render_job_id`` when given. One at a time."""
    import asyncio

    from ..composer.validation import validate_blueprint
    from .main import JOBS, VOICE_STORE, _create_job

    if req.quality not in ("fast", "studio", "ultra"):
        raise HTTPException(422, "Quality must be fast, studio or ultra.")
    if req.production not in ("lead", "doubles", "harmony", "full"):
        raise HTTPException(422, "Production must be lead, doubles, harmony or full.")
    if not validate_blueprint(req.blueprint)["ok"]:
        raise HTTPException(422, "Fix the blueprint's errors first.")
    try:
        VOICE_STORE.get(req.profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    render = None
    if req.render_job_id:
        rj = JOBS.get(req.render_job_id)
        if not rj or rj.get("kind") != "instrumental-render" or not rj.get("result"):
            raise HTTPException(404, "Render the instrumental first (renders don't survive a restart).")
        render = rj["result"]
        if render.get("blueprint_id") != req.blueprint.get("id"):
            raise HTTPException(409, "That instrumental was rendered from a different blueprint.")
    if any(j.get("kind") == "song-vocal" and j.get("stage") not in ("done", "error") for j in JOBS.values()):
        raise HTTPException(409, "A song is already being sung.")
    job_id = _create_job()
    JOBS[job_id].update(kind="song-vocal", stage="queued", pct=0.0)
    asyncio.create_task(asyncio.to_thread(_run_sing, job_id, req, render))
    return {"job_id": job_id, "status": "started"}


@router.get("/composer/sing/{job_id}/file/{name}")
def sing_file(job_id: str, name: str):
    import os

    from fastapi.responses import FileResponse

    from .main import JOBS

    job = JOBS.get(job_id)
    if not job or job.get("kind") != "song-vocal" or not job.get("result"):
        raise HTTPException(404, "No finished song with that id.")
    result = job["result"]
    path = result["backing_stems"].get(name) if name in BACKING_PARTS else result.get(SING_FILES.get(name, ""))
    if not path or not os.path.isfile(path):
        raise HTTPException(404, f"No '{name}' in this song.")
    media = "text/markdown" if path.endswith(".md") else "audio/wav"
    return FileResponse(path, media_type=media, filename=f"{name}{os.path.splitext(path)[1]}")


# ── AU-10: one prompt → a finished song in a project, stems kept ───────────

class SongRequest(BlueprintRequest):
    profile_id: str | None = None           # None: instrumental only
    production: str = "full"
    quality: str = "studio"
    project_name: str | None = None


def _run_song(job_id: str, req: SongRequest):
    import os

    from ..composer.assemble import save_song_to_project
    from ..generation import render_instrumental
    from ..voice.full_song import sing_song
    from .main import JOBS, VOICE_PROVIDER, VOICE_STORE
    from .projects import PROJECT_STORE
    from .voices import ENGINE_LOCK

    job = JOBS[job_id]
    step = lambda lo, hi: (lambda stage, pct: job.update(stage=stage, pct=lo + (hi - lo) * pct / 100.0))
    try:
        job.update(stage="writing the blueprint", pct=1.0)
        profile = VOICE_STORE.get(req.profile_id) if req.profile_id else None
        bp_req = BlueprintRequest(**{k: v for k, v in req.model_dump().items() if k in BlueprintRequest.model_fields})
        if profile is not None:
            bp_req.voice_profile_id = profile.id
        blueprint = create_blueprint(bp_req)
        job["blueprint"] = blueprint
        work = os.path.join(job["work"], "song")
        render = render_instrumental(blueprint, os.path.join(work, "render"), seed=req.seed,
                                     progress=step(3, 45 if profile else 92))
        song = None
        has_lead = any(s.get("vocal") for s in blueprint["sections"])
        if profile is not None and has_lead:
            def convert(src, dst, quality):
                job.update(stage=f"waiting for the voice engine ({profile.name})")
                with ENGINE_LOCK:
                    job.update(stage=f"converting to {profile.name} (voice engine running)")
                    VOICE_PROVIDER.convert(source_path=src, reference_path=profile.reference_path, output_path=dst,
                                           semitone_shift=0, quality=quality, checkpoint_path=profile.checkpoint_path,
                                           config_path=profile.config_path)
            song = sing_song(blueprint, render, profile, os.path.join(work, "vocals"), convert,
                             quality=req.quality, production=req.production, progress=step(45, 94))
        job.update(stage="saving the song into a new project", pct=95.0)
        saved = save_song_to_project(PROJECT_STORE, (req.project_name or blueprint["title"])[:64] or "New song",
                                     blueprint, render, song)
        job["result"] = {"project_id": saved["project_id"], "assets": saved["assets"],
                         "title": blueprint["title"], "key": blueprint["key"], "tempo": blueprint["tempo"],
                         "duration_seconds": render["duration_seconds"], "sung": song is not None,
                         "voice": profile.name if profile and song else None,
                         "master_path": (song or {}).get("song_master_path") or render.get("master_path"),
                         "after_lufs": (song or {}).get("after_lufs") or render.get("after_lufs")}
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        message = str(exc)
        if "1455" in message or "paging file" in message.lower():
            message += " (Windows ran out of memory for the voice engine: close large apps and try again.)"
        job.update(stage="error", error=message)


@router.post("/composer/song")
async def make_song(req: SongRequest):
    """One click: blueprint → instrumental → vocals in a saved voice → master, all saved to a new project."""
    import asyncio

    from .main import JOBS, VOICE_STORE, _create_job

    if req.production not in ("lead", "doubles", "harmony", "full") or req.quality not in ("fast", "studio", "ultra"):
        raise HTTPException(422, "Production must be lead/doubles/harmony/full and quality fast/studio/ultra.")
    if req.profile_id:
        try:
            VOICE_STORE.get(req.profile_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    busy = ("song-assembly", "song-vocal", "instrumental-render")
    if any(j.get("kind") in busy and j.get("stage") not in ("done", "error") for j in JOBS.values()):
        raise HTTPException(409, "Another song is being made; wait for it to finish.")
    job_id = _create_job()
    JOBS[job_id].update(kind="song-assembly", stage="queued", pct=0.0)
    asyncio.create_task(asyncio.to_thread(_run_song, job_id, req))
    return {"job_id": job_id, "status": "started"}


class RemixRequest(BaseModel):
    levels: dict = {}
    profile_id: str | None = None


@router.get("/projects/{project_id}/stems")
def project_stems(project_id: str):
    from ..composer.assemble import DEFAULT_OFFSET, remix_stems

    try:
        stems = remix_stems(_projects(), project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return [{"asset_id": a.id, "name": a.name, "part": a.metadata.get("part"), "mix_role": a.metadata.get("mix_role"),
             "default_offset_db": DEFAULT_OFFSET.get(a.metadata.get("part"), 0.0)} for a in stems]


def _run_remix(job_id: str, project_id: str, req: RemixRequest):
    import os

    from ..composer.assemble import remix_project
    from .main import JOBS

    job = JOBS[job_id]
    try:
        job["result"] = remix_project(_projects(), project_id, req.levels, os.path.join(job["work"], "remix"),
                                      profile_id=req.profile_id,
                                      progress=lambda stage, pct: job.update(stage=stage, pct=pct))
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@router.post("/projects/{project_id}/remix")
async def remix(project_id: str, req: RemixRequest):
    """Re-mix and re-master from the project's own stems (levels, mutes, solos); saved as a new master."""
    import asyncio

    from .main import JOBS, _create_job

    try:
        project = _projects().get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if project.status != "open":
        raise HTTPException(409, "Reopen this project before remixing.")
    job_id = _create_job()
    JOBS[job_id].update(kind="project-remix", stage="queued", pct=0.0, project_id=project_id)
    asyncio.create_task(asyncio.to_thread(_run_remix, job_id, project_id, req))
    return {"job_id": job_id, "status": "started"}


# ── AU-12: retrieval and the originality guard ─────────────────────────────

class RetrieveRequest(BaseModel):
    bpm: float | None = None
    mode: str | None = None
    picked: list[str] = []
    n: int = Field(5, ge=1, le=12)


@router.post("/artist/retrieve")
def retrieve_songs(req: RetrieveRequest):
    """The switched-on songs closest to a target, with the reasons."""
    from ..artist.retrieval import retrieve
    from .artist import LIBRARY

    songs = LIBRARY.songs()
    analyses = {s.id: LIBRARY.analysis(s.id) for s in songs if s.analysis_status == "done"}
    return retrieve({"bpm": req.bpm, "mode": req.mode}, songs, analyses, n=req.n, picked=req.picked)


class SimilarityRequest(BaseModel):
    blueprint: dict
    seed: int = 0
    melody_songs: int = Field(6, ge=0, le=20)


def _run_similarity(job_id: str, req: SimilarityRequest):
    from ..artist.retrieval import retrieve
    from ..artist.similarity import catalog_melody, harmony_check, melody_check
    from ..composer.arrange import arrange
    from .artist import LIBRARY
    from .main import JOBS

    job = JOBS[job_id]
    try:
        bp = req.blueprint
        job.update(stage="comparing chords with your songs", pct=5.0)
        harmony = harmony_check(bp, [c for c in _catalog() if c.get("roman_per_bar")])
        songs = LIBRARY.songs()
        analyses = {s.id: LIBRARY.analysis(s.id) for s in songs if s.analysis_status == "done"}
        with_lead = [s for s in songs if any(f.role == "lead_vocal" for f in s.files)
                     and (analyses.get(s.id) or {}).get("melody")]
        ranked = retrieve({"bpm": bp["tempo"], "mode": bp.get("mode")}, with_lead, analyses, n=len(with_lead) or 1)
        chosen = [r for r in ranked if r["song_id"] in {s.id for s in with_lead}][: req.melody_songs]
        melodies = []
        for i, r in enumerate(chosen):
            job.update(stage=f"reading your lead vocal: {r['title']} ({i + 1}/{len(chosen)})",
                       pct=10.0 + 80.0 * i / max(1, len(chosen)))
            midis = catalog_melody(LIBRARY, LIBRARY.song(r["song_id"]))
            if midis:
                melodies.append({"song_id": r["song_id"], "title": r["title"], "midis": midis})
        job.update(stage="comparing melodies", pct=92.0)
        melody = melody_check(arrange(bp, seed=req.seed)["tracks"]["melody"], melodies)
        audio = {"id": "catalog_audio", "label": "Audio fingerprint", "status": "info",
                 "detail": "Not compared: the instrumental is synthesized from the blueprint, so chords and "
                           "melody are where copying could come from."}
        job["result"] = {"checks": [harmony, melody, audio],
                         "flagged": [c["id"] for c in (harmony, melody) if c["status"] == "flag"]}
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@router.post("/composer/similarity")
async def similarity(req: SimilarityRequest):
    """Originality guard: chords vs every switched-on song; the melody guide vs your closest lead vocals."""
    import asyncio

    from .main import JOBS, _create_job

    job_id = _create_job()
    JOBS[job_id].update(kind="similarity-check", stage="queued", pct=0.0)
    asyncio.create_task(asyncio.to_thread(_run_similarity, job_id, req))
    return {"job_id": job_id, "status": "started"}
