"""My Music library endpoints: catalog folders, songs, and background analysis."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..artist.analyze import ANALYSIS_VERSION
from ..artist.library import LibraryStore

router = APIRouter(prefix="/artist", tags=["artist"])
LIBRARY = LibraryStore()


class SourceAdd(BaseModel):
    path: str


class SongUpdate(BaseModel):
    included: bool


class AnalyseRequest(BaseModel):
    song_ids: list[str] = []
    force: bool = False


def _song_row(song) -> dict:
    return {
        "id": song.id, "title": song.title, "kind": song.kind, "source_id": song.source_id,
        "location": song.location, "variants": song.variants, "included": song.included,
        "has_lyrics": bool(song.lyrics_path), "analysis_status": song.analysis_status,
        "analysed_at": song.analysed_at, "error": song.error, "summary": song.summary,
        "stem_roles": sorted({f.role for f in song.files if f.role not in ("mix", "reference")}),
        "file_count": len(song.files),
    }


@router.get("/library")
def get_library():
    return {
        "sources": [s.__dict__ for s in LIBRARY.sources()],
        "songs": [_song_row(s) for s in LIBRARY.songs()],
        "analysis_version": ANALYSIS_VERSION,
    }


@router.post("/library/sources")
def add_source(req: SourceAdd):
    try:
        source = LIBRARY.add_source(req.path.strip().strip('"'))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"source": source.__dict__, "scan": LIBRARY.rescan()}


@router.delete("/library/sources/{source_id}")
def remove_source(source_id: str):
    """Forget a folder and its analyses. The folder itself is never touched."""
    try:
        LIBRARY.remove_source(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"removed": source_id}


@router.post("/library/rescan")
def rescan():
    try:
        return LIBRARY.rescan()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/library/songs/{song_id}")
def get_song(song_id: str):
    try:
        song = LIBRARY.song(song_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    row = _song_row(song)
    row["files"] = [{"role": f.role, "name": (f.member or f.path).replace("\\", "/").split("/")[-1],
                     "in_zip": f.member is not None, "size": f.size} for f in song.files]
    row["analysis"] = LIBRARY.analysis(song_id)
    return row


@router.get("/library/songs/{song_id}/preview")
def song_preview(song_id: str):
    """Playable audio for the player bar, served only to this machine.

    A full mix streams straight from the catalog. A stem set has no mix file, so
    its stems are summed once into a 16-bit preview under the library's local
    folder (never into the catalog) and reused after that.
    """
    try:
        path = LIBRARY.preview_path(song_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return FileResponse(path, media_type=_media_type(path))


def _media_type(path) -> str:
    return {".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg",
            ".aif": "audio/aiff", ".aiff": "audio/aiff"}.get(path.suffix.lower(), "audio/wav")


@router.patch("/library/songs/{song_id}")
def update_song(song_id: str, req: SongUpdate):
    try:
        return _song_row(LIBRARY.update_song(song_id, included=req.included))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/dna")
def artist_dna(voice_profile_id: str | None = None):
    """Artist DNA from the songs currently switched on. Computed live, so it
    always reflects the latest include/exclude choices and analyses."""
    from ..artist.dna import build_dna
    from ..voice import VoiceProfileStore

    songs = LIBRARY.songs()
    analyses = {s.id: LIBRARY.analysis(s.id) for s in songs if s.analysis_status == "done"}
    voice = None
    try:
        store = VoiceProfileStore()
        if voice_profile_id:
            voice = store.get(voice_profile_id)
        else:
            profiles = store.list()
            voice = next((p for p in profiles if p.training_status == "trained"), None) or \
                (profiles[0] if profiles else None)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return build_dna(songs, analyses, voice)


def _run_analysis(job_id: str, song_ids: list[str]):
    from .main import JOBS

    job = JOBS[job_id]
    failed = []
    for index, song_id in enumerate(song_ids):
        title = LIBRARY.song(song_id).title

        def progress(stage, pct, index=index, title=title):
            overall = (index + pct / 100.0) / len(song_ids) * 100.0
            job.update(stage=f"{title}: {stage}", pct=float(overall),
                       details={"done": index, "total": len(song_ids), "current": title,
                                "failed": len(failed)})

        try:
            LIBRARY.analyse(song_id, progress=progress)
        except Exception as exc:          # recorded on the song; keep going
            failed.append({"song_id": song_id, "title": title, "error": str(exc)[:300]})
    job["result"] = {"analysed": len(song_ids) - len(failed), "failed": failed}
    job["details"] = {"done": len(song_ids), "total": len(song_ids), "current": None,
                      "failed": len(failed)}
    job.update(stage="done", pct=100.0)


@router.post("/library/analyze")
async def analyse(req: AnalyseRequest):
    from .main import JOBS, _create_job

    if any(j.get("kind") == "catalog-analysis" and j.get("stage") not in ("done", "error")
           for j in JOBS.values()):
        raise HTTPException(409, "A library analysis is already running.")
    songs = LIBRARY.songs()
    known = {s.id for s in songs}
    if req.song_ids:
        unknown = [i for i in req.song_ids if i not in known]
        if unknown:
            raise HTTPException(404, f"Unknown song(s): {', '.join(unknown)}")
        todo = req.song_ids
    else:
        todo = [s.id for s in songs if req.force or s.analysis_status != "done"
                or s.analysis_version != ANALYSIS_VERSION]
    if not todo:
        return {"job_id": None, "status": "nothing to analyse", "total": 0}
    job_id = _create_job()
    JOBS[job_id].update(kind="catalog-analysis", stage="queued", pct=0.0,
                        details={"done": 0, "total": len(todo), "current": None, "failed": 0})
    asyncio.create_task(asyncio.to_thread(_run_analysis, job_id, todo))
    return {"job_id": job_id, "status": "started", "total": len(todo)}
