"""Rendering-provider boundary (roadmap §7).

A provider turns an arrangement (note tracks from ``composer.arrange``) into
audio stems. Auralis ships one local provider (``synth``, numpy instruments).
Heavier ones (sample libraries, SoundFonts, generative-audio models) plug in
behind the same interface later, isolated like Seed-VC, so no single model
becomes a dependency of the app.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RenderResult:
    stems: dict[str, str]                      # part → WAV path
    sample_rate: int
    duration_seconds: float
    provider: str
    extras: dict[str, str] = field(default_factory=dict)   # e.g. the melody guide


class RenderProvider:
    id = "base"
    name = "Base provider"
    description = ""

    def status(self) -> dict:
        return {"id": self.id, "name": self.name, "available": True, "description": self.description}

    def render(self, arrangement: dict, out_dir: str, seed: int = 0, progress=None) -> RenderResult:
        raise NotImplementedError
