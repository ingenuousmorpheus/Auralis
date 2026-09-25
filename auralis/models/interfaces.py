"""Provider interfaces: what each kind of engine must do, independent of any one model.

The song pipeline talks only to these:

    composition ──► InstrumentalRenderer (+ SectionGenerator for chosen sections)
                ──► GuideSinger ──► VoiceConverter ──► pitch / vocal finish ──► stems ──► mix / master

Built-in implementations: the synth renderer (``generation.synth``), the
vocalise guide singer, and Seed-VC for My Voice. Future engines — a generative
section model such as ACE-Step, a lyric singer such as DiffSinger — implement
the same interfaces in ``models/builtin.py``-style adapters and are selected in
the registry; nothing else in Auralis changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .lifecycle import ManagedModel


# ── voice conversion (My Voice) ─────────────────────────────────────────────

@dataclass
class ConversionRequest:
    source_path: str                  # dry guide (or any vocal) to convert
    output_path: str
    reference_path: str               # the saved voice's reference clip
    checkpoint_path: str | None = None  # a trained voice model, when the voice has one
    config_path: str | None = None
    quality: str = "studio"           # fast | studio | ultra
    semitone_shift: int = 0
    progress: object = None


class VoiceConverter(ManagedModel):
    """Turns a vocal into a saved voice, keeping its pitch, timing and words."""

    def convert(self, request: ConversionRequest) -> dict:
        """Write ``request.output_path``; return provenance (provider, quality, …)."""
        raise NotImplementedError


# ── guide singer ────────────────────────────────────────────────────────────

class GuideSinger(ManagedModel):
    """Performs a guide score (``voice.guide.GuideNote`` list): pitch, timing, dynamics,
    breaths and, if ``sings_words``, the lyrics. It doesn't need to sound like the user."""

    sings_words: bool = False
    languages: tuple = ()

    def sing(self, score: list, total_seconds: float, seed: int = 0) -> np.ndarray:
        """Return dry mono float32 audio at 44.1 kHz, ``total_seconds`` long."""
        raise NotImplementedError


# ── generated song sections ─────────────────────────────────────────────────

@dataclass
class SectionRequest:
    blueprint: dict                   # the whole blueprint (key, tempo, era, arrangement…)
    section_id: str                   # which section to generate
    start_seconds: float
    seconds: float                    # exact length to fill (bars × bar length)
    tempo: float
    key: str
    prompt: str                       # section prompt built from the blueprint and the brief
    out_dir: str
    seed: int = 0
    stems: tuple = ("mix",)           # stems wanted, if the model can split its output


@dataclass
class SectionResult:
    paths: dict                       # stem name → WAV path (at least "mix")
    sample_rate: int
    seconds: float
    provider: str
    notes: list = field(default_factory=list)


class SectionGenerator(ManagedModel):
    """Renders one section of a blueprint as audio (texture, full arrangement, …)."""

    def generate(self, request: SectionRequest) -> SectionResult:
        raise NotImplementedError


def section_prompt(blueprint: dict, section: dict) -> str:
    """A plain-language prompt for a generative section model, from the blueprint only."""
    # vocals come from the guide singer and the user's voice, never from the section model
    arr = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in (section.get("arrangement") or {}).items()
                    if v != "off" and k not in ("lead_vocal", "backing_vocals"))
    chords = " ".join(c["chord"] for c in (section.get("chords") or [])[:8])
    era = (blueprint.get("era") or {}).get("name", "R&B")
    return (f"{era}, {section['label']}, {blueprint['tempo']:g} BPM, {blueprint['key']}, energy "
            f"{round(section.get('energy', 0.5) * 100)}%, chords {chords}, {arr}. Instrumental, no vocals.")
