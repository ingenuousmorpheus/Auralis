"""Command line for the My Music library.

    python -m auralis.artist add "D:/My Music"      add a catalog folder and scan it
    python -m auralis.artist scan                    rescan every folder
    python -m auralis.artist analyse [--all]         analyse pending/stale songs (or all)
    python -m auralis.artist list                    show the library table

Everything stays local: the index and analyses live in
%LOCALAPPDATA%/Auralis/artist, and catalog folders are only read.
"""
from __future__ import annotations

import argparse
import sys
import time

from .analyze import ANALYSIS_VERSION
from .library import LibraryStore


def _needs_analysis(song, force: bool) -> bool:
    return force or song.analysis_status in ("pending", "stale", "error", "running") or \
        song.analysis_version != ANALYSIS_VERSION


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m auralis.artist")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("folders", nargs="+")
    sub.add_parser("scan")
    analyse = sub.add_parser("analyse")
    analyse.add_argument("--all", action="store_true", help="re-analyse every song")
    analyse.add_argument("--limit", type=int, default=0)
    sub.add_parser("list")
    args = parser.parse_args(argv)

    store = LibraryStore()
    if args.command == "add":
        for folder in args.folders:
            source = store.add_source(folder)
            print(f"added {source.path}")
        print(store.rescan())
    elif args.command == "scan":
        print(store.rescan())
    elif args.command == "analyse":
        todo = [s for s in store.songs() if _needs_analysis(s, args.all)]
        if args.limit:
            todo = todo[:args.limit]
        print(f"analysing {len(todo)} song(s)", flush=True)
        failures = 0
        for i, song in enumerate(todo, 1):
            started = time.time()
            try:
                result = store.analyse(song.id)
                summary = store.song(song.id).summary
                print(f"[{i}/{len(todo)}] ok   {time.time() - started:5.0f}s  {song.title[:40]:40}  "
                      f"{summary['bpm']:6.1f} BPM  {summary['key']:10}  {result['structure'].get('roles_form', '')}",
                      flush=True)
            except Exception as exc:          # keep going; the error is stored on the song
                failures += 1
                print(f"[{i}/{len(todo)}] FAIL {song.title[:40]}: {exc}", flush=True)
        print(f"done: {len(todo) - failures} analysed, {failures} failed")
    elif args.command == "list":
        for s in store.songs():
            sm = s.summary or {}
            print(f"{s.analysis_status:8} {s.kind:8} {s.title[:44]:44} {sm.get('bpm', ''):>6} "
                  f"{sm.get('key', ''):10} {sm.get('vocal_range') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
