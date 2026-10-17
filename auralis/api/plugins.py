"""In-memory, explicitly triggered plugin discovery API."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..plugins import scan, search, recommend, CATEGORIES, TEMPLATES

router = APIRouter(prefix='/plugins', tags=['plugins'])
_catalog = {'plugins': [], 'locations': [], 'categories': CATEGORIES, 'templates': list(TEMPLATES), 'notice': 'Scan plugin folders to build your local inventory.'}

class ScanRequest(BaseModel):
    # Additional paths are explicit, session-only plugin roots, never persisted.
    paths: list[str] = Field(default_factory=list, max_length=24)

@router.post('/scan')
def discover(request: ScanRequest):
    from ..plugins import standard_roots
    global _catalog
    if any(len(p) > 1024 for p in request.paths):
        raise HTTPException(422, 'Plugin folder path too long')
    _catalog = scan([*standard_roots(), *request.paths])
    return _catalog

@router.get('')
def catalog(query: str = '', category: str = ''):
    snapshot = _catalog
    return {**snapshot, 'plugins': search(snapshot, query, category)}

@router.get('/chains')
def chain(template: str):
    try:
        return recommend(_catalog, template)
    except ValueError:
        raise HTTPException(422, 'Unknown chain template') from None
