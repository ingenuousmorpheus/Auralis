"""Engines (advanced): which model does each job, the GPU lifecycle policy, and release.

Normal Create never needs this; it lives behind Studio → Engines.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/models", tags=["engines"])


class PolicyRequest(BaseModel):
    policy: str


class SelectRequest(BaseModel):
    kind: str
    model_id: str | None = None


@router.get("")
def engines_status():
    from ..models import REGISTRY

    return REGISTRY.status()


@router.post("/policy")
def set_policy(req: PolicyRequest):
    from ..models import REGISTRY

    try:
        REGISTRY.set_policy(req.policy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return REGISTRY.status()


@router.post("/select")
def select_engine(req: SelectRequest):
    from ..models import REGISTRY

    try:
        REGISTRY.select(req.kind, req.model_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return REGISTRY.status()


@router.post("/release")
def release():
    """Unload every resident model now (frees GPU/VRAM). Waits for a running job to finish."""
    from ..models import MODELS

    return {"released": MODELS.release_all()}
