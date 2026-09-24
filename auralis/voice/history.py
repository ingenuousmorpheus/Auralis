"""Conversion history that survives restarts (My Voice "Output" list).

Every finished conversion is copied into the voice's own folder, like takes in
a Kits history, instead of living only in the job temp folder::

    %LOCALAPPDATA%/Auralis/voices/<profile_id>/history/
        index.json
        <take_id>/output.wav  input.<ext>  peaks.json

Files are copied, never moved. Ratings and notes are the singer's own feedback
("how did that sound?") and help choose takes for paired calibration later.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

_ID = re.compile(r"[a-f0-9]{12}")
_PROVENANCE = ("quality", "semitone_shift", "diffusion_steps", "model_mode", "provider", "profile_name")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VoiceHistoryStore:
    def __init__(self, voices_root: str | Path):
        self.root = Path(voices_root)
        self._lock = threading.RLock()

    def _dir(self, profile_id: str) -> Path:
        if not _ID.fullmatch(profile_id or ""):
            raise FileNotFoundError(f"Unknown voice profile: {profile_id}")
        if not (self.root / profile_id / "profile.json").is_file():
            raise FileNotFoundError(f"Unknown voice profile: {profile_id}")
        return self.root / profile_id / "history"

    def _index(self, profile_id: str) -> list[dict]:
        path = self._dir(profile_id) / "index.json"
        try:
            return json.loads(path.read_text("utf-8")) if path.is_file() else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, profile_id: str, items: list[dict]) -> None:
        folder = self._dir(profile_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "index.json.tmp"
        tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
        os.replace(tmp, folder / "index.json")

    def add(self, profile_id: str, output_path: str, input_path: str | None = None,
            input_name: str | None = None, settings: dict | None = None, job_id: str | None = None) -> dict:
        with self._lock:
            take_id = uuid.uuid4().hex[:12]
            folder = self._dir(profile_id) / take_id
            folder.mkdir(parents=True)
            shutil.copy2(output_path, folder / "output.wav")
            item = {"id": take_id, "profile_id": profile_id, "created_at": _now(), "job_id": job_id,
                    "input_name": input_name or (os.path.basename(input_path) if input_path else None),
                    "has_input": False, "rating": None, "note": "",
                    "settings": {k: v for k, v in (settings or {}).items()
                                 if k in _PROVENANCE and isinstance(v, (str, int, float, bool))}}
            if input_path and os.path.isfile(input_path):
                ext = os.path.splitext(input_path)[1].lower() or ".wav"
                shutil.copy2(input_path, folder / f"input{ext}")
                item["has_input"] = True
            info = sf.info(str(folder / "output.wav"))
            item["duration_seconds"] = round(info.frames / info.samplerate, 2)
            items = self._index(profile_id)
            items.insert(0, item)
            self._write(profile_id, items)
            return item

    def list(self, profile_id: str) -> list[dict]:
        return self._index(profile_id)

    def get(self, profile_id: str, take_id: str) -> dict:
        item = next((i for i in self._index(profile_id) if i["id"] == take_id), None)
        if item is None:
            raise FileNotFoundError(f"Unknown take: {take_id}")
        return item

    def path(self, profile_id: str, take_id: str, which: str = "output") -> Path:
        self.get(profile_id, take_id)
        folder = self._dir(profile_id) / take_id
        if which == "output":
            return folder / "output.wav"
        matches = sorted(folder.glob("input.*"))
        if not matches:
            raise FileNotFoundError("This take has no saved input.")
        return matches[0]

    def update(self, profile_id: str, take_id: str, rating: int | None = None, note: str | None = None) -> dict:
        with self._lock:
            items = self._index(profile_id)
            item = next((i for i in items if i["id"] == take_id), None)
            if item is None:
                raise FileNotFoundError(f"Unknown take: {take_id}")
            if rating is not None:
                if rating not in (-1, 0, 1):
                    raise ValueError("Rating must be -1, 0 or 1.")
                item["rating"] = rating or None
            if note is not None:
                item["note"] = note.strip()[:500]
            self._write(profile_id, items)
            return item

    def delete(self, profile_id: str, take_id: str) -> None:
        with self._lock:
            items = self._index(profile_id)
            if not any(i["id"] == take_id for i in items):
                raise FileNotFoundError(f"Unknown take: {take_id}")
            shutil.rmtree(self._dir(profile_id) / take_id, ignore_errors=True)
            self._write(profile_id, [i for i in items if i["id"] != take_id])

    def peaks(self, profile_id: str, take_id: str, which: str = "output", points: int = 600) -> list[float]:
        """Max-abs envelope for a waveform drawing, cached beside the take."""
        src = self.path(profile_id, take_id, which)
        cache = src.parent / f"peaks_{which}.json"
        if cache.is_file():
            return json.loads(cache.read_text("utf-8"))
        peaks = audio_peaks(str(src), points)
        cache.write_text(json.dumps(peaks), encoding="utf-8")
        return peaks


def audio_peaks(path: str, points: int = 600) -> list[float]:
    info = sf.info(path)
    block = max(1, info.frames // points)
    out = []
    for chunk in sf.blocks(path, blocksize=block, dtype="float32", always_2d=True):
        out.append(round(float(np.abs(chunk).max()) if chunk.size else 0.0, 3))
        if len(out) >= points:
            break
    top = max(out) if out else 1.0
    return [round(p / top, 3) if top else 0.0 for p in out]
