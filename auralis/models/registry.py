"""Which engine does which job: one selected provider per kind, with safe fallbacks.

Kinds and defaults:

    voice_converter    seed-vc      (My Voice)
    guide_singer       vocalise     (built in; "diffsinger" when installed and chosen)
    section_generator  none         (the synth renders everything; "ace-step" when
                                     installed and chosen, for sections marked for it)

Choices and the lifecycle policy are remembered in
``%LOCALAPPDATA%/Auralis/models.json``. A chosen provider that isn't installed
never breaks a job: the registry falls back to the built-in one and says so.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .builtin import ACEStepSections, DiffSingerGuide, SeedVCConverter, VocaliseGuide
from .lifecycle import ModelManager

KINDS = ("voice_converter", "guide_singer", "section_generator")
DEFAULTS = {"voice_converter": "seed-vc", "guide_singer": "vocalise", "section_generator": None}


def _config_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "models.json"


class Registry:
    def __init__(self, manager: ModelManager, config_path: str | Path | None = None, providers=None):
        self.manager = manager
        self.config_path = Path(config_path) if config_path else _config_path()
        for p in providers if providers is not None else (SeedVCConverter(), VocaliseGuide(),
                                                           ACEStepSections(), DiffSingerGuide()):
            manager.register(p)
        self.choices = dict(DEFAULTS)
        self._load()

    # ── persistence ─────────────────────────────────────────────────────
    def _load(self):
        try:
            data = json.loads(self.config_path.read_text("utf-8"))
        except (OSError, ValueError):
            return
        for kind in KINDS:
            if kind in data.get("choices", {}):
                self.choices[kind] = data["choices"][kind]
        if data.get("policy"):
            try:
                self.manager.set_policy(data["policy"])
            except ValueError:
                pass

    def _save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"choices": self.choices, "policy": self.manager.policy}, indent=2), "utf-8")
        os.replace(tmp, self.config_path)

    # ── choosing ────────────────────────────────────────────────────────
    def providers(self, kind: str) -> list:
        return [m for m in self.manager.models() if m.spec.kind == kind]

    def select(self, kind: str, model_id: str | None) -> None:
        if kind not in KINDS:
            raise ValueError(f"Unknown kind: {kind}")
        if model_id is not None:
            model = self.manager.get(model_id)
            if model.spec.kind != kind:
                raise ValueError(f"{model.spec.name} is not a {kind.replace('_', ' ')}.")
            if not model.is_installed():
                raise ValueError(f"{model.spec.name} is not installed.")
        elif kind != "section_generator":
            raise ValueError("This kind of engine is required; choose one.")
        self.choices[kind] = model_id
        self._save()

    def set_policy(self, policy: str) -> None:
        self.manager.set_policy(policy)
        self._save()

    def resolve(self, kind: str) -> tuple[object | None, str]:
        """(provider or None, a sentence explaining the choice)."""
        chosen = self.choices.get(kind)
        default = DEFAULTS[kind]
        if chosen:
            model = self.manager.get(chosen) if chosen in {m.spec.id for m in self.manager.models()} else None
            if model and model.is_installed():
                return model, f"{model.spec.name} (chosen)"
            if default and default != chosen:
                fallback = self.manager.get(default)
                return fallback, f"{fallback.spec.name} (your choice, {chosen}, isn't installed)"
        if default:
            model = self.manager.get(default)
            return model, f"{model.spec.name} (default)"
        return None, "none: the built-in synth renders every section"

    def guide_singer(self):
        return self.resolve("guide_singer")[0]

    def voice_converter(self):
        return self.resolve("voice_converter")[0]

    def section_generator(self):
        return self.resolve("section_generator")[0]

    def status(self) -> dict:
        out = self.manager.status()
        out["kinds"] = {}
        for kind in KINDS:
            model, why = self.resolve(kind)
            out["kinds"][kind] = {"active": model.spec.id if model else None, "why": why,
                                  "chosen": self.choices.get(kind),
                                  "options": [m.spec.id for m in self.providers(kind)]}
        return out
