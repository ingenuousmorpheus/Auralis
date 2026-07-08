"""Auralis FastAPI backend (Phase 1 — master-only).

Binds to 127.0.0.1 only. No external network listener. All work happens in a
per-job working directory; nothing else on disk is touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
import subprocess
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..engine.mastering import master_file
from ..engine.pipeline import run as run_pipeline
from ..engine.profiles_loader import list_profiles, load_profile
from ..voice import SeedVCProvider, VoiceProfileStore
from ..voice.finish import MODULE_PARAMS as VOCAL_RACK_MODULES
from ..voice.finish import PRESETS as VOCAL_FINISH_PRESETS
from ..voice.finish import finish_vocal
from ..voice.pitch import STYLES as PITCH_POLISH_STYLES
from ..voice.pitch import pitch_polish
from ..voice.paired import ingest_paired_calibration

app = FastAPI(title="Auralis", version="0.8.0")

# The frontend dev server runs on a different localhost port; allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORK_ROOT = os.path.join(tempfile.gettempdir(), "auralis_jobs")
os.makedirs(WORK_ROOT, exist_ok=True)

# In-process job state. Single-user desktop app: no broker needed.
JOBS: Dict[str, dict] = {}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".aif", ".aiff", ".ogg"}
VOICE_STORE = VoiceProfileStore()
VOICE_PROVIDER = SeedVCProvider()


class MasterRequest(BaseModel):
    job_id: str
    profile_id: str
    target_lufs: float | None = None
    use_reference: bool = False


class StudioTrainRequest(BaseModel):
    profile_id: str
    depth: str = "studio"


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.8.0"}


@app.get("/profiles")
def get_profiles():
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "inspired_by": p.inspired_by,
            "description": p.description,
            "default_target_lufs": p.default_target_lufs,
        }
        for p in list_profiles()
    ]


def _safe_audio_name(filename: str | None, fallback: str) -> str:
    name = os.path.basename((filename or fallback).replace("\\", "/"))
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(415, f"Unsupported audio type: {ext or 'none'}")
    safe_stem = "".join(c for c in stem if c.isalnum() or c in " ._-").strip()
    return (safe_stem or fallback)[:120] + ext


def _create_job(filename: str | None = None, input_path: str | None = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    work = os.path.join(WORK_ROOT, job_id)
    os.makedirs(work, exist_ok=True)
    JOBS[job_id] = {
        "work": work,
        "input": input_path,
        "filename": filename,
        "reference": None,
        "stems": [],
        "stage": "uploaded" if input_path else "created",
        "pct": 0.0,
        "result": None,
        "error": None,
    }
    return job_id


@app.post("/jobs")
def create_job():
    """Create an empty stem-mixing job without uploading a duplicate mixdown."""
    return {"job_id": _create_job()}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    safe_name = _safe_audio_name(file.filename, "input.wav")
    job_id = _create_job(filename=safe_name)
    work = JOBS[job_id]["work"]
    in_path = os.path.join(work, "input" + os.path.splitext(safe_name)[1])
    with open(in_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    JOBS[job_id]["input"] = in_path
    JOBS[job_id]["stage"] = "uploaded"
    return {"job_id": job_id, "filename": safe_name}


@app.post("/upload-reference/{job_id}")
async def upload_reference(job_id: str, file: UploadFile = File(...)):
    """Upload a reference track to match (Ozone-style 'match this song').

    The reference is the user's own copy, stored only in this job's working dir,
    analysed by Matchering, and never copied into the output. It is deleted when
    the job's working directory is cleaned up.
    """
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job_id")
    work = JOBS[job_id]["work"]
    safe_name = _safe_audio_name(file.filename, "reference.wav")
    ref_path = os.path.join(work, "reference" + os.path.splitext(safe_name)[1])
    with open(ref_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    JOBS[job_id]["reference"] = ref_path
    return {"job_id": job_id, "reference": safe_name}


def _run_master(job_id: str, profile_id: str, target_lufs: float | None, use_reference: bool):
    job = JOBS[job_id]
    try:
        if not job.get("input"):
            raise ValueError("No stereo mix uploaded for this job")
        profile = load_profile(profile_id)
        out_path = os.path.join(job["work"], "master.wav")
        ref = job.get("reference") if use_reference else None

        def progress(stage: str, pct: float):
            job["stage"] = stage
            job["pct"] = float(pct)

        result = master_file(
            job["input"], out_path, profile,
            target_lufs=target_lufs, reference_path=ref, progress=progress,
        )
        job["result"] = result.__dict__
        job["stage"] = "done"
        job["pct"] = 100.0
    except Exception as e:  # surface errors to the client rather than 500-ing silently
        job["error"] = str(e)
        job["stage"] = "error"


@app.post("/master")
async def master(req: MasterRequest):
    if req.job_id not in JOBS:
        raise HTTPException(404, "Unknown job_id")
    job = JOBS[req.job_id]
    if job["stage"] not in ("uploaded", "done", "error"):
        raise HTTPException(409, "This job is already running")
    job.update(stage="queued", pct=0.0, result=None, error=None)
    asyncio.create_task(asyncio.to_thread(
        _run_master, req.job_id, req.profile_id, req.target_lufs, req.use_reference))
    return {"job_id": req.job_id, "status": "started"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job_id")
    j = JOBS[job_id]
    return {"job_id": job_id, "stage": j["stage"], "pct": j["pct"],
            "result": j["result"], "error": j["error"],
            "details": j.get("details")}


@app.websocket("/ws/jobs/{job_id}")
async def job_ws(ws: WebSocket, job_id: str):
    await ws.accept()
    if job_id not in JOBS:
        await ws.send_json({"error": "unknown job"})
        await ws.close()
        return
    last = None
    while True:
        j = JOBS[job_id]
        snapshot = (j["stage"], round(j["pct"], 1))
        if snapshot != last:
            await ws.send_json({"stage": j["stage"], "pct": j["pct"],
                                "result": j["result"], "error": j["error"],
                                "details": j.get("details")})
            last = snapshot
        if j["stage"] in ("done", "error"):
            break
        await asyncio.sleep(0.15)
    await ws.close()


@app.get("/download/{job_id}")
def download(job_id: str):
    if job_id not in JOBS or not JOBS[job_id]["result"]:
        raise HTTPException(404, "No master ready for this job")
    r = JOBS[job_id]["result"]
    # Phase 2 pipeline stores master_path; Phase 1 stores output_path
    path = r.get("master_path") or r.get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The rendered file is no longer available")
    return FileResponse(path, filename="auralis_master.wav", media_type="audio/wav")


@app.get("/download-report/{job_id}")
def download_report(job_id: str):
    if job_id not in JOBS or not JOBS[job_id]["result"]:
        raise HTTPException(404, "No report ready for this job")
    path = JOBS[job_id]["result"].get("report_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "This job does not include a mix report")
    return FileResponse(path, filename="auralis_mix_report.md", media_type="text/markdown")


@app.get("/download-session/{job_id}")
def download_session(job_id: str):
    if job_id not in JOBS or not JOBS[job_id]["result"]:
        raise HTTPException(404, "No session ready for this job")
    path = JOBS[job_id]["result"].get("session_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "This job does not include session data")
    return FileResponse(path, filename="auralis_session.json", media_type="application/json")


# ── Phase 2: stem mixing endpoints ───────────────────────────────────────

class MixRequest(BaseModel):
    job_id: str
    profile_id: str
    target_lufs: float | None = None
    use_reference: bool = False
    role_overrides: dict[str, str] = Field(default_factory=dict)


@app.post("/upload-stem/{job_id}")
async def upload_stem(job_id: str, file: UploadFile = File(...)):
    """Upload one stem for mixing. Call once per stem."""
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job_id")
    work = JOBS[job_id]["work"]
    stem_dir = os.path.join(work, "stems")
    os.makedirs(stem_dir, exist_ok=True)
    fname = _safe_audio_name(file.filename, f"stem_{uuid.uuid4().hex[:6]}.wav")
    existing = {s["filename"] for s in JOBS[job_id].get("stems", [])}
    if fname in existing:
        stem, ext = os.path.splitext(fname)
        fname = f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
    stem_path = os.path.join(stem_dir, fname)
    with open(stem_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    stems = JOBS[job_id].setdefault("stems", [])
    stems.append({"filename": fname, "path": stem_path})
    return {"job_id": job_id, "stem": fname, "total_stems": len(stems)}


def _run_mix(job_id: str, profile_id: str, target_lufs: float | None,
             use_reference: bool, role_overrides: dict[str, str]):
    job = JOBS[job_id]
    try:
        stems_info = job.get("stems", [])
        if not stems_info:
            raise ValueError("No stems uploaded for this job")
        invalid_roles = set(role_overrides.values()) - {
            "vocal", "drums", "bass", "harmonic", "other"
        }
        if invalid_roles:
            raise ValueError(f"Unknown stem role(s): {', '.join(sorted(invalid_roles))}")
        stem_paths = [s["path"] for s in stems_info]
        ref = job.get("reference") if use_reference else None
        out_path = os.path.join(job["work"], "master.wav")
        path_overrides = {s["path"]: role_overrides[s["filename"]]
                         for s in stems_info if s["filename"] in role_overrides}

        def progress(stage: str, pct: float):
            job["stage"] = stage
            job["pct"] = float(pct)

        result = run_pipeline(
            stem_paths=stem_paths, output_path=out_path,
            profile_id=profile_id, reference_path=ref,
            role_overrides=path_overrides, target_lufs=target_lufs,
            progress=progress,
        )
        d = result.__dict__.copy()
        d["master_path"] = out_path
        job["result"] = d
        job["stage"] = "done"
        job["pct"] = 100.0
    except Exception as e:
        job["error"] = str(e)
        job["stage"] = "error"


@app.post("/mix")
async def mix_stems(req: MixRequest):
    """Run the full mix + master pipeline on uploaded stems."""
    if req.job_id not in JOBS:
        raise HTTPException(404, "Unknown job_id")
    job = JOBS[req.job_id]
    if job["stage"] not in ("created", "uploaded", "done", "error"):
        raise HTTPException(409, "This job is already running")
    job.update(stage="queued", pct=0.0, result=None, error=None)
    asyncio.create_task(asyncio.to_thread(
        _run_mix, req.job_id, req.profile_id,
        req.target_lufs, req.use_reference, req.role_overrides,
    ))
    return {"job_id": req.job_id, "status": "started"}


@app.get("/stems/{job_id}")
def get_stems(job_id: str):
    """Return uploaded stems with auto-detected roles if analysis has run."""
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job_id")
    job = JOBS[job_id]
    stems = job.get("stems", [])
    result = job.get("result") or {}
    analyses = result.get("stem_analyses", [])
    enriched = []
    for i, s in enumerate(stems):
        entry = {"filename": s["filename"]}
        if i < len(analyses):
            entry.update(analyses[i])
        enriched.append(entry)
    return {"job_id": job_id, "stems": enriched}


# ── Private singing voice studio ──────────────────────────────────────────

@app.get("/voice/provider")
def voice_provider_status():
    return VOICE_PROVIDER.status().__dict__


def _run_voice_provider_install(job_id: str):
    job = JOBS[job_id]
    try:
        script = Path(__file__).resolve().parents[2] / "tools" / "install_seed_vc.ps1"
        job.update(stage="installing isolated voice engine", pct=10.0)
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(script),
            ],
            capture_output=True,
            text=True,
            timeout=60 * 45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "Unknown install error")[-4000:]
            raise RuntimeError(tail)
        status = VOICE_PROVIDER.status()
        if not status.installed:
            raise RuntimeError("Installer finished but the voice engine was not found.")
        job["result"] = status.__dict__
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@app.post("/voice/provider/install")
async def install_voice_provider():
    job_id = _create_job()
    JOBS[job_id]["kind"] = "voice-provider-install"
    JOBS[job_id].update(stage="queued", pct=0.0)
    asyncio.create_task(asyncio.to_thread(_run_voice_provider_install, job_id))
    return {"job_id": job_id, "status": "started"}


@app.get("/voice/profiles")
def list_voice_profiles():
    return [profile.public_dict() for profile in VOICE_STORE.list()]


@app.post("/voice/profiles")
async def create_voice_profile(
    name: str = Form(...),
    consent_confirmed: bool = Form(...),
    file: UploadFile = File(...),
):
    safe_name = _safe_audio_name(file.filename, "voice_reference.wav")
    work = tempfile.mkdtemp(prefix="auralis_voice_profile_")
    source_path = os.path.join(work, safe_name)
    try:
        with open(source_path, "wb") as destination:
            shutil.copyfileobj(file.file, destination)
        profile = VOICE_STORE.create(name, source_path, consent_confirmed)
        return profile.public_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@app.delete("/voice/profiles/{profile_id}")
def delete_voice_profile(profile_id: str):
    try:
        VOICE_STORE.delete(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": profile_id}


@app.post("/voice/profiles/{profile_id}/recordings")
async def add_voice_recordings(
    profile_id: str,
    files: list[UploadFile] = File(...),
):
    try:
        VOICE_STORE.get(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not files:
        raise HTTPException(422, "Choose at least one vocal recording.")
    if len(files) > 100:
        raise HTTPException(422, "Upload at most 100 recordings at a time.")

    work = tempfile.mkdtemp(prefix="auralis_voice_dataset_")
    paths = []
    try:
        for index, file in enumerate(files):
            safe_name = _safe_audio_name(file.filename, f"recording_{index}.wav")
            path = os.path.join(work, f"{index:03d}_{safe_name}")
            with open(path, "wb") as destination:
                shutil.copyfileobj(file.file, destination)
            paths.append(path)
        profile = await asyncio.to_thread(
            VOICE_STORE.add_recordings, profile_id, paths
        )
        return profile.public_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@app.post("/voice/profiles/{profile_id}/paired-calibration")
async def add_paired_calibration(
    profile_id: str,
    name: str = Form("Paired calibration"),
    guide: UploadFile = File(...),
    singer: UploadFile = File(...),
):
    try:
        VOICE_STORE.get(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    work = tempfile.mkdtemp(prefix="auralis_paired_")
    try:
        guide_name = _safe_audio_name(guide.filename, "guide.wav")
        singer_name = _safe_audio_name(singer.filename, "singer.wav")
        guide_path = os.path.join(work, "guide" + os.path.splitext(guide_name)[1])
        singer_path = os.path.join(work, "singer" + os.path.splitext(singer_name)[1])
        with open(guide_path, "wb") as destination:
            shutil.copyfileobj(guide.file, destination)
        with open(singer_path, "wb") as destination:
            shutil.copyfileobj(singer.file, destination)
        profile_dir = VOICE_STORE.dataset_dir(profile_id).parent
        report = await asyncio.to_thread(
            ingest_paired_calibration,
            guide_path,
            singer_path,
            profile_dir,
            name,
        )
        singer_clips = [clip["singer_path"] for clip in report["clips"]]
        profile = await asyncio.to_thread(
            VOICE_STORE.add_recordings, profile_id, singer_clips
        )
        return {"calibration": report, "profile": profile.public_dict()}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_studio_training(job_id: str, profile_id: str, max_steps: int):
    job = JOBS[job_id]
    try:
        profile = VOICE_STORE.refresh_analysis(profile_id)
        if profile.dataset_duration_seconds < 600:
            raise ValueError("Studio training requires at least 10 minutes of prepared vocals.")
        VOICE_STORE.mark_training(
            profile_id, status="training", steps=max_steps
        )

        def progress(stage: str, pct: float, step: int, loss: float | None):
            job.update(
                stage=stage,
                pct=float(pct),
                details={"step": step, "max_steps": max_steps, "loss": loss},
            )

        profile_dir = VOICE_STORE.dataset_dir(profile_id).parent
        result = VOICE_PROVIDER.train(
            dataset_dir=str(VOICE_STORE.dataset_dir(profile_id)),
            profile_dir=str(profile_dir),
            profile_id=profile_id,
            max_steps=max_steps,
            progress=progress,
        )
        profile = VOICE_STORE.mark_training(
            profile_id,
            status="trained",
            steps=result["training_steps"],
            checkpoint_path=result["checkpoint_path"],
            config_path=result["config_path"],
        )
        result["profile"] = profile.public_dict()
        job["result"] = result
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        try:
            VOICE_STORE.mark_training(profile_id, status="error")
        except Exception:
            pass
        job.update(stage="error", error=str(exc))


@app.post("/voice/train")
async def train_studio_voice(req: StudioTrainRequest):
    if req.depth not in {"studio", "deep"}:
        raise HTTPException(422, "Training depth must be studio or deep.")
    try:
        profile = VOICE_STORE.refresh_analysis(req.profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if profile.dataset_duration_seconds < 600:
        raise HTTPException(422, "Add at least 10 minutes of clean vocals first.")
    if any(
        job.get("kind") == "voice-training"
        and job.get("stage") not in ("done", "error")
        for job in JOBS.values()
    ):
        raise HTTPException(409, "Another Studio Voice training job is already running.")

    max_steps = 1000 if req.depth == "studio" else 2500
    job_id = _create_job()
    JOBS[job_id].update(
        kind="voice-training",
        profile_id=req.profile_id,
        stage="queued",
        pct=0.0,
        details={"step": 0, "max_steps": max_steps, "loss": None},
    )
    asyncio.create_task(asyncio.to_thread(
        _run_studio_training, job_id, req.profile_id, max_steps
    ))
    return {"job_id": job_id, "status": "started", "max_steps": max_steps}


def _run_voice_conversion(
    job_id: str,
    profile_id: str,
    semitone_shift: int,
    quality: str,
):
    job = JOBS[job_id]
    try:
        profile = VOICE_STORE.get(profile_id)
        out_path = os.path.join(job["work"], "auralis_voice.wav")

        def progress(stage: str, pct: float):
            job.update(stage=stage, pct=float(pct))

        result = VOICE_PROVIDER.convert(
            source_path=job["input"],
            reference_path=profile.reference_path,
            output_path=out_path,
            semitone_shift=semitone_shift,
            quality=quality,
            checkpoint_path=profile.checkpoint_path,
            config_path=profile.config_path,
            progress=progress,
        )
        result.update(
            profile_id=profile.id,
            profile_name=profile.name,
            consent_confirmed=profile.consent_confirmed,
        )
        job["result"] = result
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@app.post("/voice/convert")
async def convert_voice(
    profile_id: str = Form(...),
    semitone_shift: int = Form(0),
    quality: str = Form("studio"),
    file: UploadFile = File(...),
):
    if quality not in {"fast", "studio", "ultra"}:
        raise HTTPException(422, "Quality must be fast, studio, or ultra.")
    if not -12 <= semitone_shift <= 12:
        raise HTTPException(422, "Semitone shift must be between -12 and +12.")
    try:
        VOICE_STORE.get(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    safe_name = _safe_audio_name(file.filename, "guide_vocal.wav")
    job_id = _create_job(filename=safe_name)
    job = JOBS[job_id]
    input_path = os.path.join(job["work"], "guide" + os.path.splitext(safe_name)[1])
    with open(input_path, "wb") as destination:
        shutil.copyfileobj(file.file, destination)
    job.update(
        input=input_path,
        kind="voice-conversion",
        stage="queued",
        pct=0.0,
    )
    asyncio.create_task(asyncio.to_thread(
        _run_voice_conversion, job_id, profile_id, semitone_shift, quality
    ))
    return {"job_id": job_id, "status": "started"}


@app.get("/voice/download/{job_id}")
def download_voice(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No converted vocal ready for this job")
    path = JOBS[job_id]["result"].get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The converted vocal is no longer available")
    return FileResponse(path, filename="auralis_my_voice.wav", media_type="audio/wav")


def _run_pitch_polish(
    job_id: str,
    source_path: str,
    style: str,
    key_override: str,
    instrumental_path: str | None,
):
    job = JOBS[job_id]
    try:
        output_path = os.path.join(job["work"], "auralis_pitch_polished.wav")
        report_path = os.path.join(job["work"], "pitch_polish_report.json")

        def progress(stage: str, pct: float):
            job.update(stage=stage, pct=float(pct))

        result = pitch_polish(
            vocal_path=source_path,
            output_path=output_path,
            style=style,
            instrumental_path=instrumental_path,
            key_override=key_override,
            report_path=report_path,
            progress=progress,
        )
        job["result"] = result
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@app.get("/voice/pitch-styles")
def pitch_polish_styles():
    labels = {
        "natural": "Natural",
        "studio": "Studio",
        "modern": "Modern",
        "hard": "Hard Tune",
    }
    return [
        {"id": key, "name": labels[key], **value}
        for key, value in PITCH_POLISH_STYLES.items()
    ]


@app.post("/voice/pitch")
async def create_pitch_polish(
    source_job_id: str = Form(...),
    style: str = Form("studio"),
    key: str = Form("auto"),
    instrumental: UploadFile | None = File(None),
):
    if source_job_id not in JOBS or not JOBS[source_job_id].get("result"):
        raise HTTPException(404, "The source vocal could not be found.")
    if style not in PITCH_POLISH_STYLES:
        raise HTTPException(422, "Unknown Pitch Polish style.")
    source_path = JOBS[source_job_id]["result"].get("output_path")
    if not source_path or not os.path.exists(source_path):
        raise HTTPException(410, "The source vocal is no longer available.")

    job_id = _create_job()
    job = JOBS[job_id]
    instrumental_path = None
    if instrumental is not None and instrumental.filename:
        safe_name = _safe_audio_name(instrumental.filename, "instrumental.wav")
        instrumental_path = os.path.join(
            job["work"], "instrumental" + os.path.splitext(safe_name)[1]
        )
        with open(instrumental_path, "wb") as destination:
            shutil.copyfileobj(instrumental.file, destination)
    job.update(
        kind="pitch-polish",
        source_job_id=source_job_id,
        stage="queued",
        pct=0.0,
    )
    asyncio.create_task(asyncio.to_thread(
        _run_pitch_polish,
        job_id,
        source_path,
        style,
        key,
        instrumental_path,
    ))
    return {"job_id": job_id, "status": "started"}


@app.get("/voice/pitch/{job_id}/download")
def download_pitch_polish(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No pitch-polished vocal is ready.")
    path = JOBS[job_id]["result"].get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The pitch-polished vocal is no longer available.")
    return FileResponse(path, filename="auralis_pitch_polished.wav", media_type="audio/wav")


@app.get("/voice/pitch/{job_id}/report")
def download_pitch_report(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No Pitch Polish report is ready.")
    path = JOBS[job_id]["result"].get("report_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The Pitch Polish report is no longer available.")
    return FileResponse(path, filename="auralis_pitch_polish.json", media_type="application/json")


def _run_vocal_finish(
    job_id: str,
    source_path: str,
    preset: str,
    intensity: float,
    instrumental_path: str | None,
    modules: dict | None = None,
):
    job = JOBS[job_id]
    try:
        output_path = os.path.join(job["work"], "auralis_finished_vocal.wav")
        preview_path = (
            os.path.join(job["work"], "auralis_context_preview.wav")
            if instrumental_path else None
        )
        report_path = os.path.join(job["work"], "vocal_finish_report.json")

        def progress(stage: str, pct: float):
            job.update(stage=stage, pct=float(pct))

        result = finish_vocal(
            vocal_path=source_path,
            output_path=output_path,
            preset=preset,
            intensity=intensity,
            instrumental_path=instrumental_path,
            preview_path=preview_path,
            report_path=report_path,
            modules=modules,
            progress=progress,
        )
        result["source_path"] = source_path
        job["result"] = result
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@app.get("/voice/finish-presets")
def vocal_finish_presets():
    names = {
        "natural": "Natural Cleanup",
        "polished-pop": "Polished Pop",
        "smooth-rnb": "Smooth R&B",
        "intimate": "Intimate Detail",
        "forward": "Forward & Dense",
    }
    return [
        {"id": key, "name": names[key], **value}
        for key, value in VOCAL_FINISH_PRESETS.items()
    ]


@app.get("/voice/rack-modules")
def vocal_rack_modules():
    """Rack module ids and their (min, max) parameter clamps for the GUI."""
    return {
        module: {param: {"min": lo, "max": hi} for param, (lo, hi) in params.items()}
        for module, params in VOCAL_RACK_MODULES.items()
    }


@app.post("/voice/finish")
async def create_vocal_finish(
    source_job_id: str = Form(""),
    preset: str = Form("polished-pop"),
    intensity: float = Form(0.75),
    modules: str = Form(""),
    instrumental: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
):
    """Finish a vocal from a prior job OR a directly uploaded file (rack mode)."""
    if preset not in VOCAL_FINISH_PRESETS:
        raise HTTPException(422, "Unknown Vocal Finish preset.")
    if not 0.0 <= intensity <= 1.0:
        raise HTTPException(422, "Intensity must be between 0 and 1.")
    module_state: dict | None = None
    if modules:
        try:
            module_state = json.loads(modules)
            if not isinstance(module_state, dict):
                raise ValueError
        except ValueError as exc:
            raise HTTPException(422, "modules must be a JSON object.") from exc

    job_id = _create_job()
    job = JOBS[job_id]

    if file is not None and file.filename:
        safe_name = _safe_audio_name(file.filename, "vocal.wav")
        source_path = os.path.join(
            job["work"], "rack_source" + os.path.splitext(safe_name)[1]
        )
        with open(source_path, "wb") as destination:
            shutil.copyfileobj(file.file, destination)
    else:
        if source_job_id not in JOBS or not JOBS[source_job_id].get("result"):
            raise HTTPException(404, "The converted vocal could not be found.")
        source_path = JOBS[source_job_id]["result"].get("output_path")
        if not source_path or not os.path.exists(source_path):
            raise HTTPException(410, "The converted vocal is no longer available.")

    instrumental_path = None
    if instrumental is not None and instrumental.filename:
        safe_name = _safe_audio_name(instrumental.filename, "instrumental.wav")
        instrumental_path = os.path.join(
            job["work"], "instrumental" + os.path.splitext(safe_name)[1]
        )
        with open(instrumental_path, "wb") as destination:
            shutil.copyfileobj(instrumental.file, destination)
    job.update(
        kind="vocal-finish",
        source_job_id=source_job_id or None,
        stage="queued",
        pct=0.0,
    )
    asyncio.create_task(asyncio.to_thread(
        _run_vocal_finish,
        job_id,
        source_path,
        preset,
        intensity,
        instrumental_path,
        module_state,
    ))
    return {"job_id": job_id, "status": "started"}


@app.get("/voice/finish/{job_id}/source")
def download_finish_source(job_id: str):
    """The unprocessed input of a finish job, for gain-matched A/B in the rack."""
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No finished vocal is ready.")
    path = JOBS[job_id]["result"].get("source_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The source vocal is no longer available.")
    return FileResponse(path, filename="auralis_vocal_source.wav", media_type="audio/wav")


@app.get("/voice/finish/{job_id}/download")
def download_finished_vocal(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No finished vocal is ready.")
    path = JOBS[job_id]["result"].get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The finished vocal is no longer available.")
    return FileResponse(path, filename="auralis_finished_vocal.wav", media_type="audio/wav")


@app.get("/voice/finish/{job_id}/preview")
def download_vocal_preview(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No context preview is ready.")
    path = JOBS[job_id]["result"].get("preview_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "This Vocal Finish did not include an instrumental.")
    return FileResponse(path, filename="auralis_vocal_preview.wav", media_type="audio/wav")


@app.get("/voice/finish/{job_id}/report")
def download_vocal_finish_report(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No Vocal Finish report is ready.")
    path = JOBS[job_id]["result"].get("report_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The Vocal Finish report is no longer available.")
    return FileResponse(path, filename="auralis_vocal_finish.json", media_type="application/json")


def _run_auto_studio_polish(
    job_id: str,
    source_path: str,
    instrumental_path: str | None,
):
    job = JOBS[job_id]
    try:
        pitch_path = os.path.join(job["work"], "01_pitch_polished.wav")
        pitch_report_path = os.path.join(job["work"], "pitch_polish_report.json")
        output_path = os.path.join(job["work"], "02_studio_polished.wav")
        preview_path = (
            os.path.join(job["work"], "studio_context_preview.wav")
            if instrumental_path else None
        )
        finish_report_path = os.path.join(job["work"], "vocal_finish_report.json")

        def pitch_progress(stage: str, pct: float):
            job.update(stage=stage, pct=float(pct * 0.48))

        pitch_result = pitch_polish(
            vocal_path=source_path,
            output_path=pitch_path,
            style="studio",
            instrumental_path=instrumental_path,
            key_override="auto",
            report_path=pitch_report_path,
            progress=pitch_progress,
        )

        def finish_progress(stage: str, pct: float):
            job.update(stage=stage, pct=float(48 + pct * 0.50))

        finish_result = finish_vocal(
            vocal_path=pitch_path,
            output_path=output_path,
            preset="polished-pop",
            intensity=0.75,
            instrumental_path=instrumental_path,
            preview_path=preview_path,
            report_path=finish_report_path,
            progress=finish_progress,
        )
        job["result"] = {
            "output_path": output_path,
            "pitch_path": pitch_path,
            "preview_path": preview_path,
            "pitch": pitch_result,
            "finish": finish_result,
        }
        job.update(stage="done", pct=100.0)
    except Exception as exc:
        job.update(stage="error", error=str(exc))


@app.post("/voice/auto-polish")
async def auto_studio_polish(
    source_job_id: str = Form(...),
    instrumental: UploadFile | None = File(None),
):
    if source_job_id not in JOBS or not JOBS[source_job_id].get("result"):
        raise HTTPException(404, "The converted vocal could not be found.")
    source_path = JOBS[source_job_id]["result"].get("output_path")
    if not source_path or not os.path.exists(source_path):
        raise HTTPException(410, "The converted vocal is no longer available.")
    job_id = _create_job()
    job = JOBS[job_id]
    instrumental_path = None
    if instrumental is not None and instrumental.filename:
        safe_name = _safe_audio_name(instrumental.filename, "instrumental.wav")
        instrumental_path = os.path.join(
            job["work"], "instrumental" + os.path.splitext(safe_name)[1]
        )
        with open(instrumental_path, "wb") as destination:
            shutil.copyfileobj(instrumental.file, destination)
    job.update(kind="auto-studio-polish", stage="queued", pct=0.0)
    asyncio.create_task(asyncio.to_thread(
        _run_auto_studio_polish, job_id, source_path, instrumental_path
    ))
    return {"job_id": job_id, "status": "started"}


@app.get("/voice/auto-polish/{job_id}/download")
def download_auto_studio_polish(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No studio-polished vocal is ready.")
    path = JOBS[job_id]["result"].get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(410, "The studio-polished vocal is no longer available.")
    return FileResponse(path, filename="auralis_studio_polished.wav", media_type="audio/wav")


@app.get("/voice/auto-polish/{job_id}/preview")
def download_auto_studio_preview(job_id: str):
    if job_id not in JOBS or not JOBS[job_id].get("result"):
        raise HTTPException(404, "No studio preview is ready.")
    path = JOBS[job_id]["result"].get("preview_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "This polish did not include an instrumental.")
    return FileResponse(path, filename="auralis_studio_preview.wav", media_type="audio/wav")
