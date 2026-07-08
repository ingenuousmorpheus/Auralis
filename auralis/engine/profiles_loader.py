"""Style profiles — measurable sonic targets, not impersonations.

A profile describes *the sound* (tonal balance, width, dynamics) and points to a
reference target. Profiles are named for the sound with an ``inspired_by`` note;
they do not name or claim to replicate any individual's process.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

PROFILES_DIR = os.path.dirname(__file__) + "/profiles"


@dataclass
class StyleProfile:
    id: str
    display_name: str
    inspired_by: str
    # Path (relative to the profiles dir) to a reference WAV used by Matchering.
    # If None, the mastering stage runs in "internal target" mode (Phase 1 may
    # ship without bundled references; see docs/profiles.md).
    reference: Optional[str] = None
    default_target_lufs: float = -14.0
    description: str = ""
    targets: dict = field(default_factory=dict)

    @property
    def reference_path(self) -> Optional[str]:
        if not self.reference:
            return None
        return os.path.join(PROFILES_DIR, self.reference)


def load_profile(profile_id: str) -> StyleProfile:
    path = os.path.join(PROFILES_DIR, f"{profile_id}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Unknown profile: {profile_id}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return StyleProfile(**data)


def list_profiles() -> list[StyleProfile]:
    out = []
    for fn in sorted(os.listdir(PROFILES_DIR)):
        if fn.endswith(".yaml"):
            out.append(load_profile(fn[:-5]))
    return out
