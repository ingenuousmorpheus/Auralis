"""My Voice library endpoints: save voices from a microphone take, voice cards,
and the conversion history.

The older ``/voice/*`` routes in ``main.py`` (profiles, datasets, paired
calibration, training, conversion, pitch, finish) are unchanged; this router
adds the Kits/Suno-style pieces on top of them.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..voice.history import VoiceHistoryStore

router = APIRouter(prefix="/voice", tags=["voice library"])

# Only one Seed-VC conversion at a time: host memory is tight, and two
# provider processes loading Whisper at once exhausted commit memory before.
ENGINE_LOCK = threading.Lock()
MAX_TAKE_BYTES = 200 * 1024 * 1024          # about 18 min of 48 kHz mono 16-bit WAV


def _store():
    from .main import VOICE_STORE

    return VOICE_STORE


def _history() -> VoiceHistoryStore:
    return VoiceHistoryStore(_store().root)


def _save_upload(upload: UploadFile, folder: str, fallback: str) -> str:
    from .main import _safe_audio_name

    name = _safe_audio_name(upload.filename, fallback)
    path = os.path.join(folder, name)
    size = 0
    with open(path, "wb") as out:
        while chunk := upload.file.read(1 << 20):
            size += len(chunk)
            if size > MAX_TAKE_BYTES:
                raise HTTPException(413, "That recording is too long; keep takes under about 15 minutes.")
            out.write(chunk)
    return path


def record_conversion(job: dict, job_id: str) -> None:
    """Called when a conversion finishes: keep it in the voice's history."""
    result = job.get("result") or {}
    profile_id = result.get("profile_id")
    if not profile_id or not result.get("output_path"):
        return
    try:
        item = _history().add(profile_id, result["output_path"], input_path=job.get("input"),
                              input_name=job.get("filename"), settings=result, job_id=job_id)
        result["history_id"] = item["id"]
    except (OSError, FileNotFoundError):
        pass                                   # history is a convenience; never fail the conversion


# ── Voices from a microphone take ──────────────────────────────────────────

@router.post("/takes/check")
async def check_take(file: UploadFile = File(...)):
    """Analyse a take without saving anything: level, noise, singing seconds,
    the reference window, and plain-language issues and tips."""
    import asyncio

    import soundfile as sf

    from ..voice.capture import analyse_take

    work = tempfile.mkdtemp(prefix="auralis_take_")
    try:
        path = _save_upload(file, work, "take.wav")
        try:
            audio, sr = sf.read(path, always_2d=True, dtype="float32")
        except RuntimeError as exc:
            raise HTTPException(415, "Auralis could not read that recording.") from exc
        report = await asyncio.to_thread(analyse_take, audio, sr)
        return report.to_dict()
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/profiles/from-take")
async def create_from_take(
    name: str = Form(...),
    consent_confirmed: bool = Form(...),
    singer_name: str = Form(""),
    file: UploadFile = File(...),
    consent_clip: UploadFile | None = File(None),
):
    """Save a new voice from one microphone take (plus an optional spoken
    consent clip, which is stored but never trained on)."""
    import asyncio

    work = tempfile.mkdtemp(prefix="auralis_take_")
    try:
        take = _save_upload(file, work, "take.wav")
        clip = _save_upload(consent_clip, work, "consent.wav") if consent_clip and consent_clip.filename else None
        profile, report = await asyncio.to_thread(
            _store().create_from_take, name, take, consent_confirmed, singer_name or None, clip)
        return {"profile": profile.public_dict(), "take": report}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/profiles/{profile_id}/takes")
async def add_take(profile_id: str, file: UploadFile = File(...)):
    """Record more singing for an existing voice (grows its dataset)."""
    import asyncio

    try:
        _store().get(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    work = tempfile.mkdtemp(prefix="auralis_take_")
    try:
        take = _save_upload(file, work, "take.wav")
        profile = await asyncio.to_thread(_store().add_take, profile_id, take)
        return {"profile": profile.public_dict(), "take": profile.last_take}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


class VoiceUpdate(BaseModel):
    name: str


@router.patch("/profiles/{profile_id}")
def rename_voice(profile_id: str, req: VoiceUpdate):
    try:
        return _store().rename(profile_id, req.name).public_dict()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/profiles/{profile_id}/reference")
def voice_reference(profile_id: str):
    """The voice's reference clip, so the voice card can play a sample."""
    try:
        profile = _store().get(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not os.path.isfile(profile.reference_path):
        raise HTTPException(404, "This voice has no reference clip.")
    return FileResponse(profile.reference_path, media_type="audio/wav", filename=f"{profile.name}_sample.wav")


# ── History ────────────────────────────────────────────────────────────────

class TakeUpdate(BaseModel):
    rating: int | None = None
    note: str | None = None


class TakeToProject(BaseModel):
    project_id: str


@router.get("/history")
def list_history(profile_id: str | None = None):
    """Conversions kept per voice, newest first. Without ``profile_id``, all voices."""
    store = _store()
    ids = [profile_id] if profile_id else [p.id for p in store.list()]
    names = {p.id: p.name for p in store.list()}
    items = []
    for pid in ids:
        try:
            items += [dict(i, profile_name=names.get(pid)) for i in _history().list(pid)]
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    return sorted(items, key=lambda i: i["created_at"], reverse=True)


def _take_path(profile_id, take_id, which="output"):
    try:
        return _history().path(profile_id, take_id, which)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/history/{profile_id}/{take_id}/audio")
def take_audio(profile_id: str, take_id: str, which: str = "output"):
    if which not in ("output", "input"):
        raise HTTPException(422, "which must be output or input")
    path = _take_path(profile_id, take_id, which)
    media = "audio/wav" if path.suffix == ".wav" else "application/octet-stream"
    return FileResponse(str(path), media_type=media, filename=f"{take_id}_{which}{path.suffix}")


@router.get("/history/{profile_id}/{take_id}/peaks")
def take_peaks(profile_id: str, take_id: str, which: str = "output"):
    _take_path(profile_id, take_id, which)
    try:
        return _history().peaks(profile_id, take_id, which)
    except RuntimeError as exc:
        raise HTTPException(415, "Could not read that audio for a waveform.") from exc


@router.patch("/history/{profile_id}/{take_id}")
def update_take(profile_id: str, take_id: str, req: TakeUpdate):
    try:
        return _history().update(profile_id, take_id, rating=req.rating, note=req.note)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/history/{profile_id}/{take_id}")
def delete_take(profile_id: str, take_id: str):
    try:
        _history().delete(profile_id, take_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": take_id}


@router.post("/history/{profile_id}/{take_id}/to-project")
def take_to_project(profile_id: str, take_id: str, req: TakeToProject):
    """Copy a kept conversion into a project (works after restarts, unlike job imports)."""
    from .projects import PROJECT_STORE

    path = _take_path(profile_id, take_id)
    item = _history().get(profile_id, take_id)
    try:
        asset = PROJECT_STORE.add_asset(
            req.project_id, path, "vocal",
            name=f"{os.path.splitext(item.get('input_name') or 'vocal')[0]}_my_voice.wav",
            origin={"type": "voice-history", "profile_id": profile_id, "take_id": take_id},
            metadata={k: v for k, v in item["settings"].items()})
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return asset.__dict__
