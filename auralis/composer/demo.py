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


def key_from_notes(notes: list[dict], extra: np.ndarray | None = None) -> tuple[int, str, float]:
    """Key from sung notes: duration-weighted pitch classes against the KK profiles,
    the last (resolving) note counted extra. Chroma of a sparse voice memo is too noisy.
    ``extra`` adds pitch-class weight from chords played in the demo."""
    hist = np.zeros(12)
    for n in notes:
        hist[int(round(n["midi"])) % 12] += n["end"] - n["start"]
    if notes:
        last = int(round(notes[-1]["midi"])) % 12
        hist[last] += 0.5 * (notes[-1]["end"] - notes[-1]["start"]) + 0.25 * hist.sum() / max(1, len(notes))
    if extra is not None and extra.sum() > 0:
        hist = hist + extra / extra.sum() * max(hist.sum(), 1.0)
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


ROMAN = ["I", "♭II", "II", "♭III", "III", "IV", "♯IV", "V", "♭VI", "VI", "♭VII", "VII"]
ACCOMP_RATIO = 0.25          # share of C2–C6 energy not explained by the melody → an instrument is playing
CHORD_STRENGTH = 0.60        # triad-template similarity for a bar's chord to count as played (measured 0.65–0.72
                             # for real played triads with overtones; the ratio gate guards voice-only memos)
TONALITY = 15.0             # dB, strongest spectral bin over the median bin (played notes ≫ flat noise)
CHORD_BINS = (36, 76)        # MIDI range used for chords: C2 up to E5 (bass and comping, not overtones)


def accompaniment(mono: np.ndarray, sr: int, notes: list[dict]) -> dict:
    """What is left of the demo once the sung melody (and its overtones) is masked out.

    A voice's own overtones include the fifth and the major third, so an unmasked chroma
    would 'hear' a major triad under any sung note. Masking the melody's harmonic series
    in a semitone CQT leaves only what an instrument plays."""
    import librosa

    y = librosa.resample(mono, orig_sr=sr, target_sr=22050) if sr != 22050 else mono
    hop = 512
    mag = np.abs(librosa.cqt(y, sr=22050, hop_length=hop, fmin=librosa.note_to_hz("C1"),
                             n_bins=84, bins_per_octave=12))
    times = librosa.frames_to_time(np.arange(mag.shape[1]), sr=22050, hop_length=hop)
    bins = 24 + np.arange(84)                                   # MIDI note of each bin
    keep = np.ones_like(mag, dtype=bool)
    for n in notes:
        sel = (times >= n["start"] - 0.04) & (times <= n["end"] + 0.08)
        for k in range(1, 13):
            h = n["midi"] + 12 * np.log2(k)
            keep[np.ix_(np.abs(bins - h) <= 1.2, sel)] = False     # CQT bins leak into neighbours
    band = (bins >= CHORD_BINS[0]) & (bins < CHORD_BINS[1])
    power = mag[band] ** 2
    frame_total = power.sum(axis=0)
    sounding = frame_total > 1e-3 * (frame_total.max() or 1.0)
    ratio = float((power * keep[band]).sum(axis=0)[sounding].sum() / max(frame_total[sounding].sum(), 1e-12))
    rest = mag * keep
    chroma = np.zeros((12, rest.shape[1]))
    for b in np.flatnonzero(band):
        chroma[bins[b] % 12] += np.log1p(rest[b] * 50) * (1.5 if bins[b] < 55 else 1.0)   # bass counts more
    energy = chroma.sum(axis=0)
    loud = energy > 0.25 * (energy.max() or 1.0)
    # tonal = played notes stand far above the median bin; room noise and hiss are flat
    residual = rest[band][:, loud]
    if residual.size:
        contrast = 20 * np.log10(np.maximum(residual.max(axis=0), 1e-12) /
                                 np.maximum(np.median(residual, axis=0), 1e-12))
        tonality = float(np.median(contrast))
    else:
        tonality = 0.0
    return {"ratio": round(ratio, 3), "chroma": chroma, "times": times, "tonality": round(tonality, 2),
            "loud_start": float(times[np.argmax(loud)]) if loud.any() else 0.0}


def _triad_templates():
    names, vecs = [], []
    for root in range(12):
        for quality, shape in (("maj", (0, 4, 7)), ("min", (0, 3, 7))):
            v = np.zeros(12)
            v[[(root + i) % 12 for i in shape]] = [1.0, 0.8, 0.9]
            names.append((root, quality))
            vecs.append(v / np.linalg.norm(v))
    return names, np.array(vecs)


def played_chords(acc: dict, bar_starts: list[float], bar_seconds: float, tonic: int) -> list[dict]:
    """Chord per bar from the masked accompaniment: [{roman, root, quality, strength}] (roman None if unclear)."""
    names, templates = _triad_templates()
    out = []
    energy = acc["chroma"].sum(axis=0)
    floor = 0.05 * (energy.max() or 1.0)
    spans = [(acc["times"] >= st) & (acc["times"] < st + bar_seconds) for st in bar_starts]
    levels = [float(energy[sp].mean()) if sp.any() else 0.0 for sp in spans]
    typical = float(np.median([lv for lv in levels if lv > 0] or [0.0]))
    for start, span, level in zip(bar_starts, spans, levels):
        sel = span & (energy > floor)
        if sel.sum() < 3 or level < 0.35 * typical:          # silence, or just a release tail
            out.append({"roman": None, "strength": 0.0})
            continue
        vec = acc["chroma"][:, sel].mean(axis=1)
        vec = vec - vec.min()
        norm = np.linalg.norm(vec)
        if norm < 1e-9:
            out.append({"roman": None, "strength": 0.0})
            continue
        scores = templates @ (vec / norm)
        best = int(np.argmax(scores))
        root, quality = names[best]
        numeral = ROMAN[(root - tonic) % 12]
        out.append({"roman": numeral.lower() if quality == "min" else numeral, "root": root, "quality": quality,
                    "strength": round(float(scores[best]), 3)})
    return out


def find_pickup(notes: list[dict], tempo: float, change_beats: list[float] | None = None) -> float:
    """Beats of pickup (anacrusis) before the first bar line: 0, 0.5, ... 3.5.

    Tries each bar-line placement and scores how well long notes (and any played chord
    changes) land on strong beats; the final note resolving on beat 1 counts double. A
    pickup is only chosen when the notes before the bar line are short and it clearly
    beats starting on the first note (inherently ambiguous otherwise)."""
    if len(notes) < 3:
        return 0.0
    spb = 60.0 / tempo
    first = notes[0]["start"]
    onsets = np.array([(n["start"] - first) / spb for n in notes])
    durs = np.array([(n["end"] - n["start"]) / spb for n in notes])

    def strength(pos):
        pos = pos % 4
        for target, w in ((0, 1.0), (2, 0.6), (1, 0.3), (3, 0.3)):
            if abs(pos - target) < 0.13 or abs(pos - target - 4) < 0.13:
                return w
        return 0.1 if abs(pos * 2 - round(pos * 2)) < 0.26 else 0.05

    def score(p):
        total = sum(strength(o - p) * (0.5 + min(d, 4.0)) for o, d in zip(onsets, durs))
        total += strength(onsets[-1] - p) * (0.5 + min(durs[-1], 4.0))          # the resolution, again
        for c in change_beats or []:
            total += 1.5 * (strength(c - p) == 1.0)
        return total

    base = score(0.0)
    best_p, best = 0.0, base
    for p in np.arange(0.5, 4.0, 0.5):
        before = onsets < p - 1e-6
        if not before.any() or durs[before].max() > 1.05 or durs[before].sum() > 2.1:
            continue                                            # pickups are a few short notes
        sc = score(p)
        if sc > best:
            best_p, best = float(p), sc
    return best_p if best > base * 1.15 else 0.0


def analyse_demo(audio: np.ndarray, sr: int, tempo_hint: float | None = None, key_hint: str | None = None,
                 pickup_beats: float | None = None) -> dict:
    """Tempo, key and melody notes of a demo (mono or stereo float audio)."""
    import librosa

    from ..artist.analyze import _to_rate, melody_notes

    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = mono.astype(np.float32)
    duration = len(mono) / sr
    got = melody_notes(_to_rate(mono, sr, target=16000))
    notes = []
    if got:
        notes_f, _, _, frame_s = got
        notes = [{"start": round(a * frame_s, 3), "end": round(b * frame_s, 3), "midi": round(m, 2)}
                 for a, b, m in notes_f]
    acc = accompaniment(mono, sr, notes)
    has_instrument = acc["ratio"] >= ACCOMP_RATIO and acc["tonality"] >= TONALITY
    if len(notes) < 3 and not has_instrument:
        raise ValueError("No clear melody was heard in the demo. Sing or play the idea a little louder and closer.")
    why = []
    if tempo_hint:
        tempo = float(tempo_hint)
        why.append(f"{tempo:.0f} BPM: you set it.")
    else:
        tempo = tempo_from_notes(notes) if len(notes) >= 6 else None
        if tempo is None:                                    # too few notes: fall back to the beat tracker
            onset = librosa.onset.onset_strength(y=mono, sr=sr)
            bpm, _ = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
            tempo = float(np.atleast_1d(bpm)[0]) or 90.0
        while tempo < 65:
            tempo *= 2
        while tempo > 145:
            tempo /= 2
        tempo = fit_tempo(notes, tempo) if notes else round(tempo, 1)
        why.append(f"{tempo:g} BPM: measured from the demo's rhythm and fitted to where your notes land "
                   "(set it yourself if it reads at half or double time).")
    extra = None
    if has_instrument:
        # pitch classes of the triads read per second (tonic-free), weighted by confidence
        extra = np.zeros(12)
        for c in played_chords(acc, list(np.arange(0.0, duration, 1.0)), 1.0, 0):
            if c.get("roman"):
                third = 3 if c["quality"] == "min" else 4
                for iv, w in ((0, 1.0), (third, 0.8), (7, 0.9)):
                    extra[(c["root"] + iv) % 12] += w * c["strength"]
    if key_hint:
        tonic, mode = parse_key(key_hint)
        why.append(f"{key_name(tonic, mode)}: you set it.")
    else:
        tonic, mode, fit = key_from_notes(notes, extra)
        why.append(f"{key_name(tonic, mode)}: from the notes you sang"
                   f"{' and the chords you played' if has_instrument else ''} (profile fit {fit:.2f}).")

    # bar grid. With an instrument, the bar line is where its chords change (how a player hears
    # it) and sung notes before it are the pickup; singing alone, the phrasing decides.
    spb = 60.0 / tempo
    sound_start = acc["loud_start"]
    first_note = notes[0]["start"] if notes else None
    chords = []
    how = "you set it"
    if pickup_beats is not None:
        pickup = float(pickup_beats)
        bar_line = (first_note if first_note is not None else sound_start) + pickup * spb
    elif has_instrument:
        grid0 = min(sound_start, first_note) if first_note is not None else sound_start
        rough = played_chords(acc, list(np.arange(grid0, duration, spb)), spb, tonic)       # per beat
        changes = [i for i in range(1, len(rough))
                   if rough[i]["roman"] and rough[i - 1]["roman"] and rough[i]["roman"] != rough[i - 1]["roman"]]
        phase = max(range(4), key=lambda ph: (sum(1 for i in changes if i % 4 == ph), -ph)) if changes else 0
        bar_line = grid0 + phase * spb
        pickup = 0.0
        if first_note is not None and first_note < bar_line - 0.25 * spb:
            pickup = min(3.5, round((bar_line - first_note) / spb * 2) / 2)
        how = "from where your chords change"
    else:
        pickup = find_pickup(notes, tempo) if notes else 0.0
        bar_line = first_note + pickup * spb
        how = "found in your phrasing"
    if pickup:
        why.append(f"Pickup: {pickup:g} beat{'s' if pickup != 1 else ''} before the first bar line ({how}).")
    kept_bars = 0
    if has_instrument:
        n_bars = max(1, int(math.ceil((duration - bar_line) / (4 * spb))))
        chords = played_chords(acc, [bar_line + i * 4 * spb for i in range(n_bars)], 4 * spb, tonic)
        kept_bars = sum(1 for c in chords if c["roman"] and c["strength"] >= CHORD_STRENGTH)
        why.append(f"An instrument is playing ({round(acc['ratio'] * 100)}% of the sound isn't the melody); "
                   f"chords read clearly in {kept_bars} of {len(chords)} bars.")
    return {"tempo": tempo, "key": key_name(tonic, mode), "tonic": tonic, "mode": mode,
            "duration_seconds": round(duration, 2), "notes": notes, "pickup_beats": pickup,
            "bar_line_seconds": round(bar_line, 3), "has_instrument": has_instrument,
            "accompaniment_ratio": acc["ratio"], "played_chords": chords, "why": why}


def melody_to_beats(notes: list[dict], tempo: float, pickup_beats: float = 0.0) -> list[tuple]:
    """Seconds → beats on a 16th grid from the first bar line. Pickup notes (anacrusis)
    get negative beats: they sound just before the section starts."""
    if not notes:
        return []
    spb = 60.0 / tempo
    t0 = notes[0]["start"] + pickup_beats * spb
    out = []
    for n in notes:
        start = round(((n["start"] - t0) / spb) / GRID) * GRID
        length = max(GRID, round(((n["end"] - n["start"]) / spb) / GRID) * GRID)
        out.append((max(-pickup_beats, start), length, int(round(n["midi"])), 90))
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

    melody = melody_to_beats(demo["notes"], demo["tempo"], demo.get("pickup_beats", 0.0))
    played = demo.get("played_chords") or []
    end_beat = max([s + l for s, l, _, _ in melody] + [4.0 * sum(1 for c in played if c.get("roman"))])
    bars = int(min(16, max(4, 4 * math.ceil(math.ceil(end_beat / 4) / 4))))
    melody = [n for n in melody if n[0] < bars * 4]
    bp = build_blueprint(prompt, lyrics, dna=dna, voice_range=voice_range, voice_name=voice_name, catalog=catalog,
                         seed=seed, tempo=demo["tempo"], key=demo["key"], **settings)
    if role not in {s["type"] for s in bp["sections"]}:
        role = "chorus" if "chorus" in {s["type"] for s in bp["sections"]} else bp["sections"][1]["type"]
    tonic, mode = parse_key(bp["key"])
    triads, why = harmonize([n for n in melody if n[0] >= 0], tonic, mode, bars)
    era_colors = next(e for e in load_atlas()["eras"] if e["id"] == bp["era"]["id"])["chord_colors"]
    roman = _colour(triads, era_colors)
    kept = 0
    for i in range(min(bars, len(played))):
        c = played[i]
        if c.get("roman") and c.get("strength", 0) >= CHORD_STRENGTH:
            roman[i] = c["roman"]                     # the chord you played, as played (triad)
            kept += 1
    if kept:
        why = [f"Chords: {kept} of {bars} bars keep the chord you played; "
               + ("the rest are written under your melody." if kept < bars else "none were changed.")]
    changes = {"sections": [
        {"id": s["id"], "bars": bars, "chords_per_bar": 1.0,
         "progression": {"roman": roman, "name": "From your demo" if kept else "Under your demo",
                         "source": "demo", "status": "your demo",
                         "sources": [], "why": why[0]}}
        if s["type"] == role else {"id": s["id"]} for s in bp["sections"]]}
    bp = revise(bp, changes, catalog=catalog)
    # "line": the user's own sung idea (the validator keeps third-party melodies out by key name)
    bp["demo"] = {"role": role, "bars": bars, "line": [list(n) for n in melody], "tempo": demo["tempo"],
                  "key": demo["key"], "note_count": len(melody), "duration_seconds": demo["duration_seconds"],
                  "pickup_beats": demo.get("pickup_beats", 0.0), "played_chord_bars": kept,
                  "has_instrument": bool(demo.get("has_instrument"))}
    bp["why"]["demo"] = demo["why"] + why + [
        (f"Your demo becomes every {role} ({bars} bars, {len(melody)} notes kept on a 16th grid); "
         if melody else f"Your chords become every {role} ({bars} bars) and the composer writes its melody; ")
        + "the composer writes the other sections around it."]
    bp["edited"] = sorted(set(bp.get("edited", [])) - {"sections"})
    return bp
