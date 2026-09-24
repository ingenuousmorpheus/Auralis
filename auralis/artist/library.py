"""My Music library: index the user's own catalog in place and store analyses.

Audio is **never copied**. The library records where each song's files live
(a loose file, a folder of stems, or members of a stems .zip), and the analysis
results go under ``%LOCALAPPDATA%/Auralis/artist/``:

    artist/
        library/library.json      folders, songs, file fingerprints
        analyses/<song-id>.json   one analysis per song

Nothing is ever written to the catalog folders. Zip members are extracted one
at a time to a temp folder for analysis and deleted straight after.

Grouping rules (a catalog is messy; these are deliberately simple and visible):

* a ``.zip`` holding audio → one stem-set song
* a folder with 2+ files that look like stems → one stem-set song; other audio
  in that folder (demo, vocal guide, full mix) is attached to it as a reference
* any other audio file → its own song
* a ``.txt`` next to a song → its lyrics (the path is linked, the text is not copied)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".aif", ".aiff", ".ogg"}

# Stem role detection from file names. Order matters: backing before lead.
_STEM_PATTERNS = [
    ("backing_vocal", r"\b(backing|bgv|bgvs|harmony|harmonies|adlibs?|background)\b.*\b(vocals?|vox)\b|\bbacking\b"),
    ("lead_vocal", r"\blead\b.*\b(vocals?|vox)\b"),
    ("vocal", r"\b(vocals?|vox|acapella|a cappella)\b"),
    ("drums", r"\b(drums?|kick|snare|hi ?hats?|perc|percussion|808s?)\b"),
    ("bass", r"\b(bass|sub)\b"),
    ("harmonic", r"\b(keys|keyboard|piano|guitar|gtr|synths?|pads?|strings|organ|rhodes|chords)\b"),
    ("other", r"\b(other|fx|sfx|ambience|atmos|texture)\b"),
]
_STEM_HINT = re.compile(r"_kits_|\(\s*(backing vocals|lead vocals|bass|drums|fx|percussion|synth|guitar|keyboard|other|strings)\s*\)|^\d+\s+\w", re.I)

_VARIANT_PATTERNS = {
    "instrumental": r"\binstrumental\b|\binst\b",
    "remix": r"\bremix\b|\bmix\b(?!.*\bmaster)",
    "cover": r"\bcover\b",
    "demo": r"\bdemo\b|\bguide\b",
    "type-beat": r"\btype beat\b",
    "live": r"\bperformance\b|\blive\b",
}


def _default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "artist"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalise(name: str) -> str:
    return re.sub(r"[_\-\.]+", " ", name).lower()


def stem_role(filename: str) -> str | None:
    """Role for a stem file name, or None when the name says nothing."""
    name = _normalise(Path(filename).stem)
    for role, pattern in _STEM_PATTERNS:
        if re.search(pattern, name):
            return role
    return None


def is_kits_instrumental(filename: str) -> bool:
    """KITS exports name the instrumental '..._backing_KITS_...', not a backing vocal."""
    return bool(re.search(r"_backing_kits_", Path(filename).name, re.I))


def looks_like_stem(filename: str) -> bool:
    """A named stem: a stem word plus a stem-export pattern, or a short bare name like 'bass.wav'."""
    if is_kits_instrumental(filename) or stem_role(filename) is None:
        return False
    return bool(_STEM_HINT.search(Path(filename).name)) or \
        len(_normalise(Path(filename).stem).split()) <= 3


def variants(title: str) -> list[str]:
    name = _normalise(title)
    return [tag for tag, pattern in _VARIANT_PATTERNS.items() if re.search(pattern, name)]


def clean_title(name: str) -> str:
    title = re.sub(r"(\.(zip|wav|mp3|flac|aiff?|ogg))+$", "", name, flags=re.I)
    title = re.sub(r"^\d{1,2}\s+", "", title)                       # track numbers
    title = re.sub(r"\bstems?\b", "", title, flags=re.I)
    title = re.sub(r"[_]+", " ", title)
    return re.sub(r"\s{2,}", " ", title).strip(" -") or name


@dataclass
class SongFile:
    role: str                    # stem role, "mix", or "reference"
    path: str                    # file path, or the .zip path for members
    member: str | None = None    # zip member name
    size: int = 0


@dataclass
class Song:
    id: str
    title: str
    kind: str                    # "mix" | "stem-set"
    source_id: str
    location: str                # folder, file or zip, relative to the source root
    variants: list[str] = field(default_factory=list)
    files: list[SongFile] = field(default_factory=list)
    lyrics_path: str | None = None
    fingerprint: str = ""
    included: bool = True        # user can exclude songs from Artist DNA
    analysis_status: str = "pending"   # pending | done | error | stale
    analysed_at: str | None = None
    analysis_version: int | None = None
    error: str | None = None
    summary: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Song":
        data = dict(data)
        data["files"] = [SongFile(**f) for f in data.get("files", [])]
        return cls(**data)


@dataclass
class Source:
    id: str
    path: str
    added_at: str
    scanned_at: str | None = None


# ── Scanning ───────────────────────────────────────────────────────────────

def scan_source(root: str | Path, source_id: str, skipped: list | None = None) -> list[Song]:
    """Walk one catalog folder and group its files into songs. Read-only.

    Lone stems (one stem among song versions) are not songs; their paths are
    appended to ``skipped`` when a list is given.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder not found: {root}")
    songs: list[Song] = []
    for folder, dirnames, filenames in os.walk(root):
        dirnames.sort()
        folder_path = Path(folder)
        audio = sorted(f for f in filenames if Path(f).suffix.lower() in AUDIO_EXTENSIONS)
        texts = sorted(f for f in filenames if f.lower().endswith(".txt"))
        zips = sorted(f for f in filenames if f.lower().endswith(".zip"))

        for zname in zips:
            song = _zip_song(folder_path / zname, root, source_id)
            if song:
                song.lyrics_path = _match_lyrics(song.title, folder_path, texts)
                songs.append(song)

        stems = [f for f in audio if looks_like_stem(f)]
        if len(stems) >= 2:
            files = [SongFile(role=stem_role(f) or "other", path=str(folder_path / f),
                              size=(folder_path / f).stat().st_size) for f in stems]
            for f in audio:
                if f not in stems:
                    files.append(SongFile(role="reference", path=str(folder_path / f),
                                          size=(folder_path / f).stat().st_size))
            title = clean_title(folder_path.name)
            songs.append(_make_song(title, "stem-set", source_id, folder_path, root, files,
                                    lyrics=str(folder_path / texts[0]) if texts else None))
            continue

        for f in audio:
            if f in stems:
                if skipped is not None:
                    skipped.append(str(folder_path / f))
                continue    # a lone stem among song versions is not a song
            path = folder_path / f
            title = clean_title(re.sub(r"_backing_KITS_.*(?=\.\w+$)", " (Instrumental)", f, flags=re.I))
            songs.append(_make_song(title, "mix", source_id, path, root,
                                    [SongFile(role="mix", path=str(path), size=path.stat().st_size)],
                                    lyrics=_match_lyrics(title, folder_path, texts,
                                                         fallback_single=len(audio) == 1)))
    return songs


def _zip_song(zpath: Path, root: Path, source_id: str) -> Song | None:
    try:
        with zipfile.ZipFile(zpath) as archive:
            members = [i for i in archive.infolist()
                       if not i.is_dir() and Path(i.filename).suffix.lower() in AUDIO_EXTENSIONS
                       and not Path(i.filename).name.startswith("._")]
    except zipfile.BadZipFile:
        return None
    if not members:
        return None
    files = []
    for info in members:
        role = stem_role(info.filename)
        files.append(SongFile(role=role or ("mix" if len(members) == 1 else "other"),
                              path=str(zpath), member=info.filename, size=info.file_size))
    kind = "stem-set" if len(members) >= 2 else "mix"
    return _make_song(clean_title(zpath.name), kind, source_id, zpath, root, files)


def _make_song(title, kind, source_id, location: Path, root: Path, files, lyrics=None) -> Song:
    rel = str(location.relative_to(root)).replace("\\", "/")
    fingerprint = hashlib.sha1(json.dumps(
        [(f.path, f.member, f.size) for f in files]).encode("utf-8")).hexdigest()[:16]
    song_id = hashlib.sha1(f"{source_id}:{rel}".encode("utf-8")).hexdigest()[:12]
    return Song(id=song_id, title=title, kind=kind, source_id=source_id, location=rel,
                variants=variants(location.name if kind == "stem-set" else title),
                files=files, lyrics_path=lyrics, fingerprint=fingerprint)


def _match_lyrics(title: str, folder: Path, texts: list[str], fallback_single=False) -> str | None:
    words = set(_normalise(title).split()) - {"remix", "stems", "rnb", "the", "a", "1", "2"}
    best, best_score = None, 0
    for t in texts:
        overlap = len(words & set(_normalise(Path(t).stem).split()))
        if overlap > best_score:
            best, best_score = t, overlap
    if best and best_score >= min(2, len(words)):
        return str(folder / best)
    if fallback_single and len(texts) == 1:
        return str(folder / texts[0])
    return None


# ── Loading audio ──────────────────────────────────────────────────────────

class SongAudio:
    """Load a song's mix and stems, extracting zip members to temp one at a time."""

    def __init__(self, song: Song):
        self.song = song

    def load(self) -> tuple[np.ndarray, int, dict[str, np.ndarray]]:
        """Return (stereo mix, sr, stems by role as mono arrays at sr)."""
        import soundfile as sf

        if self.song.kind == "mix":
            f = self.song.files[0]
            audio, sr = self._read(f, sf)
            return audio, sr, {}

        # Stems are summed as they are read so peak memory is ~one stem plus the
        # running mix and per-role totals, not every stem at once.
        mix = np.zeros((0, 2), dtype=np.float32)
        summed: dict[str, np.ndarray] = {}
        sr_out = None
        for f in self.song.files:
            if f.role == "reference":
                continue
            audio, sr = self._read(f, sf)
            if sr_out is None:
                sr_out = sr
            elif sr != sr_out:
                from math import gcd
                from scipy.signal import resample_poly
                g = gcd(sr, sr_out)
                audio = resample_poly(audio, sr_out // g, sr // g, axis=0).astype(np.float32)
            stereo = audio[:, :2] if audio.shape[1] >= 2 else np.repeat(audio[:, :1], 2, axis=1)
            mix = _add_into(mix, stereo)
            summed[f.role] = _add_into(summed.get(f.role, np.zeros(0, np.float32)),
                                       audio.mean(axis=1).astype(np.float32))
            del audio, stereo
        if sr_out is None:
            raise ValueError("No stems could be read.")
        return mix, sr_out, summed

    @staticmethod
    def _read(f: SongFile, sf):
        if f.member is None:
            return _read_any(f.path, sf)
        temp = tempfile.mkdtemp(prefix="auralis_catalog_")
        try:
            with zipfile.ZipFile(f.path) as archive:
                target = Path(temp) / ("member" + Path(f.member).suffix.lower())
                with archive.open(f.member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
            return _read_any(str(target), sf)
        finally:
            shutil.rmtree(temp, ignore_errors=True)


def _add_into(total: np.ndarray, part: np.ndarray) -> np.ndarray:
    """total + part, growing total when part is longer (stems can differ by a few samples)."""
    if len(part) > len(total):
        grown = np.zeros((len(part),) + total.shape[1:], dtype=np.float32)
        grown[: len(total)] = total
        total = grown
    total[: len(part)] += part
    return total


def _read_any(path: str, sf) -> tuple[np.ndarray, int]:
    try:
        audio, sr = sf.read(path, always_2d=True, dtype="float32")
    except Exception:
        import librosa  # mp3 fallback via audioread/soundfile backends
        mono, sr = librosa.load(path, sr=None, mono=False)
        audio = mono.T if mono.ndim == 2 else mono[:, np.newaxis]
    return audio.astype(np.float32), int(sr)


# ── Store ──────────────────────────────────────────────────────────────────

class LibraryStore:
    """Library index + per-song analyses under the user's local app data."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else _default_root()
        (self.root / "library").mkdir(parents=True, exist_ok=True)
        (self.root / "analyses").mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index_path = self.root / "library" / "library.json"

    # index
    def _load(self) -> dict:
        if not self._index_path.exists():
            return {"schema_version": 1, "sources": [], "songs": []}
        return json.loads(self._index_path.read_text("utf-8"))

    def _save(self, data: dict) -> None:
        temp = self._index_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, self._index_path)

    def sources(self) -> list[Source]:
        return [Source(**s) for s in self._load()["sources"]]

    def songs(self) -> list[Song]:
        return [Song.from_dict(s) for s in self._load()["songs"]]

    def song(self, song_id: str) -> Song:
        for s in self.songs():
            if s.id == song_id:
                return s
        raise FileNotFoundError(f"Unknown song: {song_id}")

    def add_source(self, path: str) -> Source:
        folder = Path(path)
        if not folder.is_dir():
            raise FileNotFoundError(f"Folder not found: {path}")
        with self._lock:
            data = self._load()
            resolved = os.path.abspath(str(folder))
            for s in data["sources"]:
                if s["path"] == resolved:
                    return Source(**s)
            source = Source(id=hashlib.sha1(resolved.lower().encode()).hexdigest()[:12],
                            path=resolved, added_at=_now())
            data["sources"].append(asdict(source))
            self._save(data)
            return source

    def remove_source(self, source_id: str) -> None:
        with self._lock:
            data = self._load()
            if not any(s["id"] == source_id for s in data["sources"]):
                raise FileNotFoundError(f"Unknown source: {source_id}")
            gone = [s["id"] for s in data["songs"] if s["source_id"] == source_id]
            data["sources"] = [s for s in data["sources"] if s["id"] != source_id]
            data["songs"] = [s for s in data["songs"] if s["source_id"] != source_id]
            self._save(data)
            for song_id in gone:
                self._forget(song_id)

    def rescan(self) -> dict:
        """Re-walk every source. Keeps analyses of unchanged songs; marks changed ones stale."""
        with self._lock:
            data = self._load()
            old = {s["id"]: Song.from_dict(s) for s in data["songs"]}
            found: list[Song] = []
            skipped: list[str] = []
            for src in data["sources"]:
                for song in scan_source(src["path"], src["id"], skipped):
                    prev = old.get(song.id)
                    if prev:
                        song.included = prev.included
                        song.summary = prev.summary
                        song.analysed_at = prev.analysed_at
                        song.analysis_version = prev.analysis_version
                        song.error = prev.error
                        song.analysis_status = (prev.analysis_status
                                                if prev.fingerprint == song.fingerprint else "stale")
                    found.append(song)
                src["scanned_at"] = _now()
            data["songs"] = [asdict(s) for s in found]
            self._save(data)
            ids = {s.id for s in found}
            removed = [i for i in old if i not in ids]
            for song_id in removed:
                self._forget(song_id)
            return {"songs": len(found), "new": len(ids - set(old)), "removed": len(removed),
                    "skipped_lone_stems": len(skipped)}

    def update_song(self, song_id: str, **fields) -> Song:
        with self._lock:
            data = self._load()
            for s in data["songs"]:
                if s["id"] == song_id:
                    s.update(fields)
                    self._save(data)
                    return Song.from_dict(s)
            raise FileNotFoundError(f"Unknown song: {song_id}")

    def _forget(self, song_id: str) -> None:
        """Drop a song's derived files: its analysis and any cached preview."""
        (self.root / "analyses" / f"{song_id}.json").unlink(missing_ok=True)
        for preview in (self.root / "previews").glob(f"{song_id}_*.wav"):
            preview.unlink(missing_ok=True)

    def resummarise(self) -> int:
        """Rebuild table summaries from saved analyses (after a summary format change)."""
        with self._lock:
            data = self._load()
            count = 0
            for s in data["songs"]:
                analysis = self.analysis(s["id"])
                if analysis and s.get("analysis_status") == "done":
                    s["summary"] = summarise(analysis)
                    count += 1
            self._save(data)
            return count

    def preview_path(self, song_id: str) -> Path:
        """A playable file for the song: the mix itself, or a cached stem mixdown."""
        import soundfile as sf

        song = self.song(song_id)
        if song.kind == "mix":
            path = Path(song.files[0].path)
            if not path.is_file():
                raise FileNotFoundError("The song file is no longer in its folder.")
            return path
        previews = self.root / "previews"
        previews.mkdir(exist_ok=True)
        target = previews / f"{song_id}_{song.fingerprint}.wav"
        if target.is_file():
            return target
        with self._lock:
            if target.is_file():
                return target
            for stale in previews.glob(f"{song_id}_*.wav"):
                stale.unlink(missing_ok=True)
            mix, sr, _ = SongAudio(song).load()
            peak = float(np.max(np.abs(mix))) if mix.size else 0.0
            if peak > 0.98:                       # summed stems can clip
                mix = mix * np.float32(0.98 / peak)
            temp = target.with_suffix(".tmp.wav")
            sf.write(temp, mix, sr, subtype="PCM_16")
            os.replace(temp, target)
        return target

    # analyses
    def analysis(self, song_id: str) -> dict | None:
        path = self.root / "analyses" / f"{song_id}.json"
        return json.loads(path.read_text("utf-8")) if path.exists() else None

    def analyse(self, song_id: str, progress=None) -> dict:
        from .analyze import ANALYSIS_VERSION, analyse_song

        song = self.song(song_id)
        self.update_song(song_id, analysis_status="running", error=None)
        try:
            if progress:
                progress("reading audio", 0)
            mix, sr, stems = SongAudio(song).load()
            result = analyse_song(mix, sr, stems, progress=progress)
            result["song_id"] = song_id
            result["stems_used"] = sorted(stems)
            path = self.root / "analyses" / f"{song_id}.json"
            temp = path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(result, indent=1), encoding="utf-8")
            os.replace(temp, path)
            self.update_song(song_id, analysis_status="done", analysed_at=_now(),
                             analysis_version=ANALYSIS_VERSION, summary=summarise(result))
            return result
        except Exception as exc:
            self.update_song(song_id, analysis_status="error", error=str(exc)[:500])
            raise


def summarise(analysis: dict) -> dict:
    """The few fields the library table shows."""
    melody = analysis.get("melody") or {}
    return {
        "duration_seconds": analysis["global"]["duration_seconds"],
        "bpm": analysis["tempo"]["bpm"],
        "key": analysis["key"]["name"],
        "key_confidence": analysis["key"]["confidence"],
        "lufs": analysis["global"]["integrated_lufs"],
        "form": analysis["structure"].get("form", ""),
        "roles_form": analysis["structure"].get("roles_form", ""),
        "sections": len(analysis["structure"].get("sections", [])),
        "vocal_range": (f"{melody['range_low_note']}–{melody['range_high_note']}"
                        if melody else None),
        "chords_per_bar": analysis["harmony"]["changes_per_bar"],
        "vocal_melody_found": analysis["global"].get("vocal_melody_found"),
    }
