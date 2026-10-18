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

from .builtin import ACEStepSections, DiffSingerGuide, SeedVCConverter, VocaliseGuide, WordGuide
from .lifecycle import ModelManager

KINDS = ("voice_converter", "guide_singer", "section_generator")
# The word guide sings the lyrics' words (owner-approved default, Session 032); vocalise
# (melody on vowels) is the fallback where no speech voice exists, e.g. outside Windows.
DEFAULTS = {"voice_converter": "seed-vc", "guide_singer": "word-guide", "section_generator": None}
FALLBACKS = {"guide_singer": "vocalise"}
# Settings saved before the word guide existed hold "vocalise" only because it was the sole
# choice; without this marker that value is not a deliberate choice and the default applies.
GUIDE_CHOICE_MARK = "guide_choice_since_word_guide"


def _config_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "models.json"


class Registry:
    def __init__(self, manager: ModelManager, config_path: str | Path | None = None, providers=None):
        self.manager = manager
        self.config_path = Path(config_path) if config_path else _config_path()
        for p in providers if providers is not None else (SeedVCConverter(), VocaliseGuide(), WordGuide(),
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
                if (kind == "guide_singer" and data["choices"][kind] == "vocalise"
                        and not data.get(GUIDE_CHOICE_MARK)):
                    continue                                   # saved before there was a choice
                self.choices[kind] = data["choices"][kind]
        if data.get("policy"):
            try:
                self.manager.set_policy(data["policy"])
            except ValueError:
                pass

    def _save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"choices": self.choices, "policy": self.manager.policy,
                                   GUIDE_CHOICE_MARK: True}, indent=2), "utf-8")
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
                model, _ = self._default(kind, default)
                return model, f"{model.spec.name} (your choice, {chosen}, isn't installed)"
        if default:
            return self._default(kind, default)
        return None, "none: the built-in synth renders every section"

    def _default(self, kind: str, default: str) -> tuple[object, str]:
        """The default for ``kind``, or its fallback where the default can't run here."""
        known = {m.spec.id for m in self.manager.models()}
        model = self.manager.get(default) if default in known else None
        fallback = FALLBACKS.get(kind)
        if (model is None or not model.is_installed()) and fallback in known:
            spare = self.manager.get(fallback)
            return spare, f"{spare.spec.name} (default {model.spec.name if model else default} isn't available here)"
        if model is None:
            raise KeyError(f"Unknown model: {default}")
        return model, f"{model.spec.name} (default)"

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
