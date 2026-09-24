"""My Music library and Artist DNA (catalog analysis). Local-only."""

from .library import LibraryStore, Song, scan_source

__all__ = ["LibraryStore", "Song", "scan_source"]
