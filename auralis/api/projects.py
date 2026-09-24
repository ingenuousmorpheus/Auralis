"""Project endpoints: create, list, open, close, and save work into a project."""
from __future__ import annotations

import os
import shutil
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..projects import ASSET_KINDS, ProjectStore
from ..projects.jobs import job_kind, job_outputs

router = APIRouter(prefix="/projects", tags=["projects"])
PROJECT_STORE = ProjectStore()


class ProjectCreate(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    name: str | None = None
    voice_profile_id: str | None = None


class JobImport(BaseModel):
    job_id: str


def _summary(project) -> dict:
    data = project.to_dict()
    data.pop("history", None)
    data["asset_count"] = len(project.assets)
    data.pop("assets", None)
    return data


def _get(project_id: str):
    try:
        return PROJECT_STORE.get(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def list_projects():
    return [_summary(p) for p in PROJECT_STORE.list()]


@router.post("")
def create_project(req: ProjectCreate):
    try:
        return PROJECT_STORE.create(req.name).to_dict()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{project_id}")
def get_project(project_id: str):
    project = _get(project_id)
    return {**project.to_dict(), "integrity": PROJECT_STORE.verify(project_id)}


@router.patch("/{project_id}")
def update_project(project_id: str, req: ProjectUpdate):
    _get(project_id)
    try:
        if req.name is not None:
            PROJECT_STORE.rename(project_id, req.name)
        if "voice_profile_id" in req.model_fields_set:
            PROJECT_STORE.set_voice_profile(project_id, req.voice_profile_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return PROJECT_STORE.get(project_id).to_dict()


@router.post("/{project_id}/open")
def open_project(project_id: str):
    _get(project_id)
    project = PROJECT_STORE.open(project_id)
    return {**project.to_dict(), "integrity": PROJECT_STORE.verify(project_id)}


@router.post("/{project_id}/close")
def close_project(project_id: str):
    _get(project_id)
    return _summary(PROJECT_STORE.close(project_id))


@router.delete("/{project_id}")
def delete_project(project_id: str):
    _get(project_id)
    PROJECT_STORE.delete(project_id)
    return {"deleted": project_id}


@router.get("/{project_id}/verify")
def verify_project(project_id: str, deep: bool = False):
    _get(project_id)
    return PROJECT_STORE.verify(project_id, deep=deep)


@router.post("/{project_id}/assets")
async def upload_asset(
    project_id: str,
    kind: str = Form("source"),
    file: UploadFile = File(...),
):
    """Add a file straight from disk (e.g. a source song or a stem)."""
    from .main import _safe_audio_name

    _get(project_id)
    if kind not in ASSET_KINDS:
        raise HTTPException(422, f"Kind must be one of: {', '.join(ASSET_KINDS)}")
    safe_name = _safe_audio_name(file.filename, f"{kind}.wav")
    work = tempfile.mkdtemp(prefix="auralis_project_upload_")
    try:
        path = os.path.join(work, safe_name)
        with open(path, "wb") as destination:
            shutil.copyfileobj(file.file, destination)
        asset = PROJECT_STORE.add_asset(
            project_id, path, kind, origin={"type": "upload"},
        )
        return asset.__dict__
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/{project_id}/import-job")
def import_job(project_id: str, req: JobImport):
    """Copy a finished job's inputs and outputs into the project."""
    from .main import JOBS

    project = _get(project_id)
    if project.status != "open":
        raise HTTPException(409, "Reopen this project before adding files.")
    job = JOBS.get(req.job_id)
    if job is None:
        raise HTTPException(404, "Unknown job_id (jobs do not survive a backend restart).")
    already = {a.origin.get("job_id") for a in project.assets}
    if req.job_id in already:
        raise HTTPException(409, "This job is already saved in the project.")
    try:
        outputs = job_outputs(job)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    kind = job_kind(job)
    assets = []
    for output in outputs:
        asset = PROJECT_STORE.add_asset(
            project_id, output.path, output.kind, name=output.name,
            origin={"type": "job", "job_id": req.job_id, "job_kind": kind,
                    "role": output.role},
            metadata=output.metadata,
        )
        assets.append(asset.__dict__)
    return {"project_id": project_id, "job_id": req.job_id, "job_kind": kind,
            "assets": assets}


@router.get("/{project_id}/assets/{asset_id}")
def download_asset(project_id: str, asset_id: str):
    try:
        path = PROJECT_STORE.asset_path(project_id, asset_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, filename=path.name)


@router.delete("/{project_id}/assets/{asset_id}")
def delete_asset(project_id: str, asset_id: str):
    project = _get(project_id)
    if project.status != "open":
        raise HTTPException(409, "Reopen this project before removing files.")
    try:
        PROJECT_STORE.remove_asset(project_id, asset_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": asset_id}
