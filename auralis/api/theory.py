"""R&B Theory Atlas endpoints: eras, sources, and candidate retrieval."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..theory import candidates, eras, load_atlas

router = APIRouter(prefix="/theory", tags=["theory"])


@router.get("/eras")
def list_eras():
    return eras()


@router.get("/sources")
def list_sources():
    return load_atlas()["sources"]


@router.get("/candidates")
def get_candidates(era: str, section: str | None = None, harmony: str | None = None,
                   vocal: str | None = None, groove: str | None = None, n: int = 3,
                   use_voice: bool = True, use_dna: bool = True):
    """Several documented, transposable options for an era.

    Keys are fitted to the trained voice's range and weighted toward the
    artist's own key families (Artist DNA) unless those are switched off.
    """
    voice_range, families = None, None
    if use_voice:
        from .main import VOICE_STORE

        profiles = VOICE_STORE.list()
        voice = next((p for p in profiles if p.training_status == "trained"), None) or \
            (profiles[0] if profiles else None)
        if voice and voice.pitch_low_midi is not None and voice.pitch_high_midi is not None:
            voice_range = (voice.pitch_low_midi, voice.pitch_high_midi)
    if use_dna:
        from .artist import artist_dna

        dna = artist_dna()
        families = [f["major_tonic"] for f in dna.get("traits", {}).get("key", {}).get("families", [])] or None
    try:
        result = candidates(era, section=section, harmony=harmony, vocal=vocal, groove=groove,
                            n=max(1, min(n, 6)), voice_range=voice_range, dna_key_families=families)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    result["fitted_to"] = {"voice_range_midi": voice_range, "dna_key_families": families}
    return result
