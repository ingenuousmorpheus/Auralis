"""Demo-to-song (AU-13): a voice memo or rough idea becomes a structured song that keeps it.

    demo audio ──► tempo, key, melody notes   (analysis reused: pYIN notes from the library,
                                                beat tracking, key detection from voice/pitch)
    melody ──────► beats on a 16th grid       (the idea, preserved)
    melody ──────► chords per bar             (harmonized with the key's chords: the chord
                                                that holds the most melody, weighted by length
                                                and strong beats, then era colour)
    everything ──► a blueprint                (the demo becomes the hook or verse; the rest of
                                                the form, arrangement and atmosphere as usual)

The demo's own melody is kept note for note (quantized) in its sections; the
composer only writes melodies for the other sections. Nothing is uploaded.
"""
from __future__ import annotations

import math

import numpy as np

from .chords import chord_tones, key_name, parse_key

TRIADS = {"major": ["I", "ii", "iii", "IV", "V", "vi"], "minor": ["i", "iv", "v", "♭III", "♭VI", "♭VII", "V"]}
GRID = 0.25                                        # sixteenth notes
# Krumhansl–Kessler key profiles
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def key_from_notes(notes: list[dict]) -> tuple[int, str, float]:
    """Key from sung notes: duration-weighted pitch classes against the KK profiles,
    the last (resolving) note counted extra. Chroma of a sparse voice memo is too noisy."""
    hist = np.zeros(12)
    for n in notes:
        hist[int(round(n["midi"])) % 12] += n["end"] - n["start"]
    last = int(round(notes[-1]["midi"])) % 12
    hist[last] += 0.5 * (notes[-1]["end"] - notes[-1]["start"]) + 0.25 * hist.sum() / max(1, len(notes))
    best = (-2.0, 0, "major")
    for tonic in range(12):
        for mode, prof in (("major", _KK_MAJOR), ("minor", _KK_MINOR)):
            r = float(np.corrcoef(hist, np.roll(prof, tonic))[0, 1])
            if r > best[0]:
                best = (r, tonic, mode)
    return best[1], best[2], round(best[0], 3)


def tempo_from_notes(notes: list[dict]) -> float | None:
    """The most common gap between sung note onsets is usually one beat (or half of one):
    a steadier clock for a voice memo than the onset envelope, whose soft attacks invite
    3:2 and 4:3 readings (AU-13 finding)."""
    onsets = np.array([n["start"] for n in notes])
    ioi = np.diff(onsets)
    ioi = ioi[(ioi >= 0.15) & (ioi <= 1.5)]
    if len(ioi) < 5:
        return None
    grid = np.arange(0.15, 1.5, 0.005)
    density = np.array([np.sum(np.exp(-0.5 * ((ioi - g) / 0.02) ** 2)) for g in grid])
    return 60.0 / float(grid[int(np.argmax(density))])


def fit_tempo(notes: list[dict], estimate: float) -> float:
    """Refine a tempo so the sung onsets land on the eighth-note grid (±4% search)."""
    onsets = np.array([n["start"] for n in notes]) - notes[0]["start"]
    best = (1e9, estimate)
    for bpm in np.arange(estimate * 0.96, estimate * 1.04 + 1e-9, 0.1):
        eighths = onsets * bpm / 60.0 * 2
        cost = float(np.mean(np.abs(eighths - np.round(eighths))))
        if cost < best[0] - 1e-9:
            best = (cost, round(float(bpm), 1))
    return best[1]


def analyse_demo(audio: np.ndarray, sr: int, tempo_hint: float | None = None, key_hint: str | None = None) -> dict:
    """Tempo, key and melody notes of a demo (mono or stereo float audio)."""
    import librosa

    from ..artist.analyze import _to_rate, melody_notes

    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = mono.astype(np.float32)
    duration = len(mono) / sr
    got = melody_notes(_to_rate(mono, sr, target=16000))
    if not got:
        raise ValueError("No clear melody was heard in the demo. Sing or play the idea a little louder and closer.")
    notes_f, _, _, frame_s = got
    notes = [{"start": round(a * frame_s, 3), "end": round(b * frame_s, 3), "midi": round(m, 2)} for a, b, m in notes_f]
    why = []
    if tempo_hint:
        tempo = float(tempo_hint)
        why.append(f"{tempo:.0f} BPM: you set it.")
    else:
        tempo = tempo_from_notes(notes)
        if tempo is None:                                    # too few notes: fall back to the beat tracker
            onset = librosa.onset.onset_strength(y=mono, sr=sr)
            bpm, _ = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
            tempo = float(np.atleast_1d(bpm)[0]) or 90.0
        while tempo < 65:
            tempo *= 2
        while tempo > 145:
            tempo /= 2
        tempo = fit_tempo(notes, tempo)
        why.append(f"{tempo:g} BPM: measured from the demo's rhythm and fitted to where your notes land "
                   "(set it yourself if it reads at half or double time).")
    if key_hint:
        tonic, mode = parse_key(key_hint)
        why.append(f"{key_name(tonic, mode)}: you set it.")
    else:
        tonic, mode, fit = key_from_notes(notes)
        why.append(f"{key_name(tonic, mode)}: from the notes you sang (profile fit {fit:.2f}; the last note counts extra).")
    return {"tempo": tempo, "key": key_name(tonic, mode), "tonic": tonic, "mode": mode,
            "duration_seconds": round(duration, 2), "notes": notes, "why": why}


def melody_to_beats(notes: list[dict], tempo: float) -> list[tuple]:
    """Seconds → beats on a 16th grid, with the first sung note on the first bar line."""
    spb = 60.0 / tempo
    t0 = notes[0]["start"]
    out = []
    for n in notes:
        start = round(((n["start"] - t0) / spb) / GRID) * GRID
        length = max(GRID, round(((n["end"] - n["start"]) / spb) / GRID) * GRID)
        out.append((max(0.0, start), length, int(round(n["midi"])), 90))
    # no overlaps after quantizing
    cleaned = []
    for s, l, p, v in sorted(out):
        if cleaned and s < cleaned[-1][0] + cleaned[-1][1]:
            ps, pl, pp, pv = cleaned[-1]
            if s <= ps:
                continue
            cleaned[-1] = (ps, s - ps, pp, pv)
        cleaned.append((s, l, p, v))
    return cleaned


def harmonize(melody: list[tuple], tonic: int, mode: str, bars: int) -> tuple[list[str], list[str]]:
    """One chord per bar holding the most melody (weighted by length and strong beats)."""
    options = TRIADS[mode]
    tones = {r: {(chord_tones(r, tonic, mode)[0] + i) % 12 for i in chord_tones(r, tonic, mode)[1]} for r in options}
    roots = {r: chord_tones(r, tonic, mode)[0] for r in options}
    chosen, why = [], []
    tonic_chord = options[0]
    for bar in range(bars):
        b0, b1 = bar * 4.0, bar * 4.0 + 4.0
        weight = {r: 0.0 for r in options}
        for s, l, p, _ in melody:
            overlap = max(0.0, min(s + l, b1) - max(s, b0))
            if not overlap:
                continue
            strong = 1.5 if abs((s - b0) % 2) < 1e-6 and b0 <= s < b1 else 1.0
            for r in options:
                if p % 12 in tones[r]:
                    w = 1.0 if p % 12 == roots[r] else 0.85
                    weight[r] += overlap * strong * w
        if bar in (0, bars - 1):
            weight[tonic_chord] += 0.6                         # start and end at home
        if len(chosen) >= 2 and chosen[-1] == chosen[-2]:
            weight[chosen[-1]] -= 0.3                          # gently avoid a third bar of the same chord
        best = max(options, key=lambda r: (round(weight[r], 6), -options.index(r)))
        chosen.append(best)
    why.append("Chords written under your melody: each bar takes the key chord that holds the most of its "
               "notes (longer and on-the-beat notes count more), starting and ending at home.")
    return chosen, why


def build_from_demo(demo: dict, prompt: str = "", lyrics: str = "", role: str = "chorus", *, dna=None,
                    voice_range=None, voice_name=None, catalog=None, seed: int = 0, **settings) -> dict:
    """A full blueprint whose ``role`` sections carry the demo's melody and harmony."""
    from .blueprint import _colour, build_blueprint, revise
    from ..theory import load_atlas

    melody = melody_to_beats(demo["notes"], demo["tempo"])
    end_beat = max(s + l for s, l, _, _ in melody)
    bars = int(min(16, max(4, 4 * math.ceil(math.ceil(end_beat / 4) / 4))))
    melody = [n for n in melody if n[0] < bars * 4]
    bp = build_blueprint(prompt, lyrics, dna=dna, voice_range=voice_range, voice_name=voice_name, catalog=catalog,
                         seed=seed, tempo=demo["tempo"], key=demo["key"], **settings)
    if role not in {s["type"] for s in bp["sections"]}:
        role = "chorus" if "chorus" in {s["type"] for s in bp["sections"]} else bp["sections"][1]["type"]
    tonic, mode = parse_key(bp["key"])
    triads, why = harmonize(melody, tonic, mode, bars)
    era_colors = next(e for e in load_atlas()["eras"] if e["id"] == bp["era"]["id"])["chord_colors"]
    roman = _colour(triads, era_colors)
    changes = {"sections": [
        {"id": s["id"], "bars": bars, "chords_per_bar": 1.0,
         "progression": {"roman": roman, "name": "Under your demo", "source": "demo", "status": "your demo",
                         "sources": [], "why": why[0]}}
        if s["type"] == role else {"id": s["id"]} for s in bp["sections"]]}
    bp = revise(bp, changes, catalog=catalog)
    # "line": the user's own sung idea (the validator keeps third-party melodies out by key name)
    bp["demo"] = {"role": role, "bars": bars, "line": [list(n) for n in melody], "tempo": demo["tempo"],
                  "key": demo["key"], "note_count": len(melody), "duration_seconds": demo["duration_seconds"]}
    bp["why"]["demo"] = demo["why"] + why + [
        f"Your demo becomes every {role} ({bars} bars, {len(melody)} notes kept on a 16th grid); "
        "the composer writes the other sections around it."]
    bp["edited"] = sorted(set(bp.get("edited", [])) - {"sections"})
    return bp
