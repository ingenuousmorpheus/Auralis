"""Local project registry: one folder per song, surviving backend restarts.

Jobs live in memory and in a temp folder, so their outputs are unreachable once
the backend restarts. A project is the durable home for a song: every source,
stem, vocal, mix, master and report is copied into the project folder and
recorded in ``project.json`` with where it came from.

Layout::

    %LOCALAPPDATA%/Auralis/projects/<project-id>/
        project.json
        sources/ stems/ vocals/ mixes/ masters/ reports/ generated/

Paths in ``project.json`` are relative to the project folder so a project can
be moved or backed up as a unit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

# Asset kind → folder inside the project.
ASSET_KINDS = {
    "source": "sources",
    "stem": "stems",
    "vocal": "vocals",
    "mix": "mixes",
    "master": "masters",
    "report": "reports",
    "generated": "generated",
}

_ID_PATTERN = re.compile(r"[a-f0-9]{12}")


def _default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "projects"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_filename(name: str, fallback: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = "".join(c for c in stem if c.isalnum() or c in " ._-").strip()[:100]
    ext = "".join(c for c in ext.lower() if c.isalnum() or c == ".")[:10]
    return (stem or fallback) + ext


@dataclass
class ProjectAsset:
    id: str
    kind: str
    name: str
    path: str                 # relative to the project folder, forward slashes
    size_bytes: int
    sha256: str
    created_at: str
    origin: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class Project:
    id: str
    name: str
    created_at: str
    updated_at: str
    status: str = "open"      # "open" | "closed"
    last_opened_at: str | None = None
    closed_at: str | None = None
    voice_profile_id: str | None = None
    schema_version: int = SCHEMA_VERSION
    assets: list[ProjectAsset] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        data = dict(data)
        data["assets"] = [ProjectAsset(**a) for a in data.get("assets", [])]
        return cls(**data)


class ProjectStore:
    """Stores projects under the current Windows user's local data."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ── Projects ─────────────────────────────────────────────────────────

    def create(self, name: str) -> Project:
        clean = self._clean_name(name)
        with self._lock:
            project_id = uuid.uuid4().hex[:12]
            project_dir = self.root / project_id
            project_dir.mkdir(parents=True, exist_ok=False)
            for folder in ASSET_KINDS.values():
                (project_dir / folder).mkdir()
            now = _now()
            project = Project(
                id=project_id, name=clean, created_at=now, updated_at=now,
                last_opened_at=now,
            )
            self._log(project, "created", clean)
            self._save(project)
            return project

    def list(self) -> list[Project]:
        projects = []
        for metadata in self.root.glob("*/project.json"):
            try:
                projects.append(Project.from_dict(json.loads(metadata.read_text("utf-8"))))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def get(self, project_id: str) -> Project:
        metadata = self._project_dir(project_id) / "project.json"
        if not metadata.exists():
            raise FileNotFoundError(f"Unknown project: {project_id}")
        return Project.from_dict(json.loads(metadata.read_text("utf-8")))

    def rename(self, project_id: str, name: str) -> Project:
        clean = self._clean_name(name)
        with self._lock:
            project = self.get(project_id)
            project.name = clean
            self._log(project, "renamed", clean)
            self._save(project)
            return project

    def set_voice_profile(self, project_id: str, voice_profile_id: str | None) -> Project:
        with self._lock:
            project = self.get(project_id)
            project.voice_profile_id = voice_profile_id
            self._log(project, "voice profile set", voice_profile_id or "none")
            self._save(project)
            return project

    def open(self, project_id: str) -> Project:
        with self._lock:
            project = self.get(project_id)
            project.status = "open"
            project.last_opened_at = _now()
            self._log(project, "opened")
            self._save(project)
            return project

    def close(self, project_id: str) -> Project:
        with self._lock:
            project = self.get(project_id)
            project.status = "closed"
            project.closed_at = _now()
            self._log(project, "closed")
            self._save(project)
            return project

    def delete(self, project_id: str) -> None:
        project_dir = self._project_dir(project_id)
        if not (project_dir / "project.json").exists():
            raise FileNotFoundError(f"Unknown project: {project_id}")
        with self._lock:
            shutil.rmtree(project_dir)

    # ── Assets ───────────────────────────────────────────────────────────

    def add_asset(
        self,
        project_id: str,
        source_path: str | Path,
        kind: str,
        name: str | None = None,
        origin: dict | None = None,
        metadata: dict | None = None,
    ) -> ProjectAsset:
        """Copy a file into the project and record it. The source is left untouched."""
        if kind not in ASSET_KINDS:
            raise ValueError(f"Unknown asset kind: {kind}")
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"File not found: {source.name}")
        with self._lock:
            project = self.get(project_id)
            if project.status != "open":
                raise PermissionError("Reopen this project before adding files.")
            project_dir = self._project_dir(project_id)
            folder = project_dir / ASSET_KINDS[kind]
            folder.mkdir(exist_ok=True)
            filename = self._unique_name(folder, _safe_filename(name or source.name, kind))
            destination = folder / filename
            shutil.copy2(source, destination)
            asset = ProjectAsset(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                name=filename,
                path=f"{ASSET_KINDS[kind]}/{filename}",
                size_bytes=destination.stat().st_size,
                sha256=_sha256(destination),
                created_at=_now(),
                origin=origin or {"type": "file"},
                metadata=metadata or {},
            )
            project.assets.append(asset)
            self._log(project, "asset added", f"{kind}: {filename}")
            self._save(project)
            return asset

    def remove_asset(self, project_id: str, asset_id: str) -> None:
        with self._lock:
            project = self.get(project_id)
            asset = self._find_asset(project, asset_id)
            path = self._resolve(project_id, asset.path)
            if path.exists():
                path.unlink()
            project.assets = [a for a in project.assets if a.id != asset_id]
            self._log(project, "asset removed", f"{asset.kind}: {asset.name}")
            self._save(project)

    def asset_path(self, project_id: str, asset_id: str) -> Path:
        project = self.get(project_id)
        asset = self._find_asset(project, asset_id)
        path = self._resolve(project_id, asset.path)
        if not path.is_file():
            raise FileNotFoundError(f"Asset file is missing: {asset.name}")
        return path

    def verify(self, project_id: str, deep: bool = False) -> dict:
        """Check every recorded asset is still on disk (and unchanged when ``deep``)."""
        project = self.get(project_id)
        missing, changed = [], []
        for asset in project.assets:
            path = self._resolve(project_id, asset.path)
            if not path.is_file():
                missing.append(asset.id)
            elif path.stat().st_size != asset.size_bytes or (
                deep and _sha256(path) != asset.sha256
            ):
                changed.append(asset.id)
        return {
            "asset_count": len(project.assets),
            "missing": missing,
            "changed": changed,
            "linked": not missing and not changed,
            "deep": deep,
        }

    # ── Song blueprint (AU-04) ────────────────────────────────────────────

    def save_blueprint(self, project_id: str, blueprint: dict) -> dict:
        """Write ``blueprint.json`` (current) and ``blueprints/r0001.json``...
        (every saved revision), plus ``lyrics.txt`` when there are lyrics."""
        with self._lock:
            project = self.get(project_id)
            if project.status != "open":
                raise PermissionError("Reopen this project before saving a blueprint.")
            project_dir = self._project_dir(project_id)
            folder = project_dir / "blueprints"
            folder.mkdir(exist_ok=True)
            saved = len(list(folder.glob("r*.json"))) + 1
            data = dict(blueprint, saved_revision=saved, saved_at=_now(), project_id=project_id)
            text = json.dumps(data, indent=2, ensure_ascii=False)
            (folder / f"r{saved:04d}.json").write_text(text, encoding="utf-8")
            temp = project_dir / "blueprint.json.tmp"
            temp.write_text(text, encoding="utf-8")
            os.replace(temp, project_dir / "blueprint.json")
            lyrics = (blueprint.get("lyrics") or "").strip()
            if lyrics:
                (project_dir / "lyrics.txt").write_text(lyrics + "\n", encoding="utf-8")
            self._log(project, "blueprint saved",
                      f"r{saved}: {blueprint.get('key')}, {blueprint.get('tempo')} BPM")
            self._save(project)
            return data

    def blueprint(self, project_id: str) -> dict | None:
        path = self._project_dir(project_id) / "blueprint.json"
        self.get(project_id)
        return json.loads(path.read_text("utf-8")) if path.is_file() else None

    def blueprint_revisions(self, project_id: str) -> list[dict]:
        self.get(project_id)
        folder = self._project_dir(project_id) / "blueprints"
        out = []
        for path in sorted(folder.glob("r*.json")) if folder.is_dir() else []:
            data = json.loads(path.read_text("utf-8"))
            out.append({"saved_revision": data.get("saved_revision"), "saved_at": data.get("saved_at"),
                        "key": data.get("key"), "tempo": data.get("tempo"), "title": data.get("title")})
        return out

    # ── Internals ────────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        if not _ID_PATTERN.fullmatch(project_id or ""):
            raise FileNotFoundError(f"Unknown project: {project_id}")
        return self.root / project_id

    def _resolve(self, project_id: str, relative: str) -> Path:
        project_dir = self._project_dir(project_id).resolve()
        path = (project_dir / relative).resolve()
        if project_dir not in path.parents:
            raise FileNotFoundError("Asset path escapes the project folder.")
        return path

    def _save(self, project: Project) -> None:
        project.updated_at = _now()
        project_dir = self._project_dir(project.id)
        target = project_dir / "project.json"
        temp = project_dir / "project.json.tmp"
        temp.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
        os.replace(temp, target)

    @staticmethod
    def _log(project: Project, action: str, detail: str = "") -> None:
        project.history.append({"at": _now(), "action": action, "detail": detail})

    @staticmethod
    def _find_asset(project: Project, asset_id: str) -> ProjectAsset:
        for asset in project.assets:
            if asset.id == asset_id:
                return asset
        raise FileNotFoundError(f"Unknown asset: {asset_id}")

    @staticmethod
    def _unique_name(folder: Path, filename: str) -> str:
        if not (folder / filename).exists():
            return filename
        stem, ext = os.path.splitext(filename)
        return f"{stem}_{uuid.uuid4().hex[:6]}{ext}"

    @staticmethod
    def _clean_name(name: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9 ._'()&-]+", "", name or "").strip()[:80]
        if not clean:
            raise ValueError("Project name is required.")
        return clean
