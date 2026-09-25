"""Atmosphere Engine (AU-06, roadmap §8): the "world" around the song.

Plans and renders section-aware texture layers from the blueprint, so the
atmosphere follows the key (every pitched layer uses the key's chords), the
tempo (rhythmic layers sit on the beat grid, swells land on downbeats) and the
energy curve (layer gains and filter brightness follow it bar by bar):

* **bed**      the whole song: vinyl crackle (vintage eras), air (modern) or room tone
* **drone**    a tonic-and-fifth pedal under intros, verses and outros; darker when quiet
* **pad**      wide sustained chord colour in choruses, bridges and interludes
* **shimmer**  high chord tones that rise through pre-choruses and float over choruses
* **choir**    an "ah" vocal-texture pad on the chords in big sections
* **sparkle**  ear candy: an eighth-note bell arpeggio of the chord tones
* **swell**    a reversed rise into every section that lifts the energy
* **tail**     the last chord ringing out after the song

What each section gets comes from its ``atmos`` level in the blueprint
arrangement (off / light / medium / full, editable like the other roles), the
era's palette and the Artist DNA; every layer records why it is there.
Deterministic DSP only, like the synth provider.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import oaconvolve, sawtooth

from .synth import SR, _bp, _hp, _hz, _lp, _reverb_ir

LEVEL_GAIN = {"off": 0.0, "light": 0.4, "medium": 0.65, "full": 0.9}
LEVELS = ["off", "light", "medium", "full"]

# Era palettes. Editorial starting points (like the arrangement palettes),
# labelled that way in the blueprint.
ERA = {
    "70s_soul":        {"bed": "vinyl", "pad": "warm",  "choir": True,  "sparkle": False, "shift": -1,
                        "why": "live-band eras keep atmosphere light: warm pads, vinyl air, a gospel-style choir"},
    "80s_quiet_storm": {"bed": "vinyl", "pad": "glass", "choir": True,  "sparkle": True,  "shift": 0,
                        "why": "Quiet Storm lives on glassy pads and slow shimmer over a pedal"},
    "90s_rnb":         {"bed": "room",  "pad": "warm",  "choir": True,  "sparkle": True,  "shift": 0,
                        "why": "90s R&B uses string-like pads and stacked-vocal textures in the hooks"},
    "neo_soul":        {"bed": "vinyl", "pad": "warm",  "choir": False, "sparkle": True,  "shift": -1,
                        "why": "neo-soul keeps the space dusty and warm, with little synthetic wash"},
    "2000s_rnb":       {"bed": "air",   "pad": "glass", "choir": True,  "sparkle": True,  "shift": 0,
                        "why": "2000s R&B contrasts sparse verses with wide, glossy choruses"},
    "modern_alt_rnb":  {"bed": "air",   "pad": "dark",  "choir": True,  "sparkle": True,  "shift": 1,
                        "why": "in modern alternative R&B texture and atmosphere are structural material"},
}
DEFAULT_ATMOS = {"intro": "medium", "verse": "light", "pre-chorus": "medium", "chorus": "full",
                 "bridge": "full", "instrumental": "full", "outro": "medium"}


def era_level(section_type: str, era: str) -> str:
    """Default atmosphere level for a section, shifted by the era's taste."""
    base = LEVELS.index(DEFAULT_ATMOS.get(section_type, "light"))
    shifted = max(0, min(3, base + ERA.get(era, ERA["2000s_rnb"])["shift"]))
    if section_type == "verse" and shifted == 0:
        shifted = 1                       # a verse always keeps at least a bed and a drone
    return LEVELS[shifted]


def describe(era: str, dna: dict | None = None) -> dict:
    """Palette and reasons for the blueprint's arrangement panel."""
    e = ERA.get(era, ERA["2000s_rnb"])
    layers = [{"vinyl": "vinyl crackle bed", "air": "airy noise bed", "room": "room-tone bed"}[e["bed"]],
              "tonic drone under verses", f"{e['pad']} chorus pad", "rising shimmer into choruses"]
    if e["choir"]:
        layers.append("'ah' choir texture in big sections")
    if e["sparkle"]:
        layers.append("bell sparkle arpeggios")
    layers.append("reverse swells into every lift")
    why = [f"Atmosphere palette: {e['why']}."]
    prod = (dna or {}).get("traits", {}).get("production") or {}
    if prod.get("stereo_width") is not None:
        w = prod["stereo_width"]
        why.append(f"Your mixes are {'narrow' if w < 0.3 else 'wide'} (width {w:.2f}), so verse atmosphere stays "
                   f"{'centred and quiet' if w < 0.3 else 'wide'} and the choruses open it up.")
    return {"layers": layers, "status": "editorial default, not Atlas research", "why": why}


# ── Planning ────────────────────────────────────────────────────────────────

def _chord_pcs(chord, tonic, mode):
    from ..composer.chords import ChordError, chord_tones

    try:
        root, tones, _ = chord_tones(chord["roman"], tonic, mode)
    except ChordError:
        return None
    return [(root + t) % 12 for t in tones]


def _place(pcs, lo, hi, n=4):
    out = []
    for pc in pcs[:n]:
        p = lo + ((pc - lo) % 12)
        while p > hi:
            p -= 12
        out.append(p)
    return sorted(set(out))


def plan_atmosphere(blueprint: dict) -> dict:
    """Blueprint → atmosphere layers, each with timing, pitches, gain, energy and a reason."""
    from ..composer.chords import parse_key

    tonic, mode = parse_key(blueprint["key"])
    era = (blueprint.get("era") or {}).get("id", "2000s_rnb")
    pal = ERA.get(era, ERA["2000s_rnb"])
    curve = blueprint.get("energy_curve") or []
    sections = blueprint["sections"]
    layers = []

    def level_of(s):
        return (s.get("arrangement") or {}).get("atmos") or era_level(s["type"], era)

    total_beats = blueprint["total_bars"] * 4.0
    layers.append({"kind": "bed", "style": pal["bed"], "start": 0.0, "beats": total_beats, "pitches": [],
                   "gain": 0.25, "section": "whole song",
                   "why": f"{pal['bed']} bed for the whole song, following the energy curve"})
    t_low = 36 + tonic if 36 + tonic >= 38 else 48 + tonic          # tonic in octave 2 (D2–C♯3)
    for i, s in enumerate(sections):
        level = level_of(s)
        g = LEVEL_GAIN[level]
        start = (s["start_bar"] - 1) * 4.0
        beats = s["bars"] * 4.0
        label = s.get("label", s["type"])
        nxt = sections[i + 1] if i + 1 < len(sections) else None
        if g:
            if s["type"] in ("intro", "verse", "outro", "pre-chorus"):
                fifth = t_low + 7
                handover = s["type"] == "pre-chorus"
                layers.append({"kind": "drone", "start": start, "beats": beats,
                               "pitches": [t_low, fifth, t_low + 12], "gain": g * 0.35, "section": label,
                               "fade_out": handover,
                               "why": f"{label}: tonic-and-fifth pedal" + (
                                   ", fading out as the shimmer rises into the chorus" if handover
                                   else "; it darkens when the energy drops")})
            chords = s.get("chords") or []
            big = s["type"] in ("chorus", "bridge", "instrumental")
            for c in chords:
                pcs = _chord_pcs(c, tonic, mode)
                if not pcs:
                    continue
                c0 = start + (c["bar"] - 1) * 4 + (c["beat"] - 1)
                if big:
                    layers.append({"kind": "pad", "style": pal["pad"], "start": c0, "beats": c["beats"],
                                   "pitches": _place(pcs, 55, 79, 5), "gain": g * 0.85, "section": label,
                                   "why": f"{label}: wide {pal['pad']} pad on {c['chord']}"})
                if s["type"] == "pre-chorus" or (big and level in ("medium", "full")):
                    layers.append({"kind": "shimmer", "start": c0, "beats": c["beats"],
                                   "pitches": _place(pcs, 76, 96, 3), "gain": g * 0.45, "section": label,
                                   "rise": s["type"] == "pre-chorus",
                                   "why": f"{label}: {'rising ' if s['type'] == 'pre-chorus' else ''}shimmer on {c['chord']}"})
                if pal["choir"] and big and level == "full":
                    layers.append({"kind": "choir", "start": c0, "beats": c["beats"],
                                   "pitches": _place(pcs, 55, 72, 3), "gain": g * 0.5, "section": label,
                                   "why": f"{label}: 'ah' vocal texture on {c['chord']}"})
                if pal["sparkle"] and big and level in ("medium", "full"):
                    layers.append({"kind": "sparkle", "start": c0, "beats": c["beats"],
                                   "pitches": _place(pcs, 72, 91, 4), "gain": g * 0.3, "section": label,
                                   "why": f"{label}: eighth-note bell sparkle on {c['chord']}"})
        # a reversed swell into any section that lifts the energy
        if nxt is not None and (nxt["energy"] >= s["energy"] + 0.1 or nxt["type"] == "chorus") \
                and LEVEL_GAIN[level_of(nxt)] and nxt.get("chords"):
            pcs = _chord_pcs(nxt["chords"][0], tonic, mode)
            if pcs:
                length = 4.0 if s["bars"] >= 2 else 2.0
                layers.append({"kind": "swell", "start": start + beats - length, "beats": length,
                               "pitches": _place(pcs, 60, 84, 4), "gain": 0.55, "section": f"into {nxt.get('label')}",
                               "why": f"reversed swell lifting into {nxt.get('label')} "
                                      f"(energy {round(s['energy'] * 100)} → {round(nxt['energy'] * 100)})"})
    last = sections[-1]
    if last.get("chords"):
        pcs = _chord_pcs(last["chords"][-1], tonic, mode)
        if pcs:
            layers.append({"kind": "tail", "start": total_beats, "beats": 8.0, "pitches": _place(pcs, 55, 79, 4),
                           "gain": 0.5, "section": "ending", "why": "the last chord rings out after the song"})
    counts = {}
    for l in layers:
        counts[l["kind"]] = counts.get(l["kind"], 0) + 1
    return {"era": era, "palette": describe(era), "layers": layers, "counts": counts,
            "energy_curve": curve, "levels": [level_of(s) for s in sections]}


# ── Rendering ───────────────────────────────────────────────────────────────

class _Voices:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed + 101)

    def noise(self, n):
        return self.rng.standard_normal(n).astype(np.float32)

    def sines(self, pitches, n, detune=0.0, octave_mix=0.0):
        t = np.arange(n) / SR
        out = np.zeros((n, 2), np.float32)
        for k, p in enumerate(pitches):
            f = _hz(p)
            for ch, d in ((0, -detune), (1, detune)):
                ph = 2 * np.pi * f * 2 ** (d / 1200) * t + k
                out[:, ch] += np.sin(ph) + octave_mix * np.sin(2 * ph)
        return out / max(1, len(pitches))

    def saws(self, pitches, n, detune=8.0):
        t = np.arange(n) / SR
        out = np.zeros((n, 2), np.float32)
        for k, p in enumerate(pitches):
            f = _hz(p)
            for ch, d in ((0, -detune), (1, detune)):
                out[:, ch] += sawtooth(2 * np.pi * f * 2 ** (d / 1200) * t + k * 0.7).astype(np.float32)
        return out / max(1, len(pitches))


def _fade(n, attack, release):
    env = np.ones(n, np.float32)
    a, r = min(n, int(attack * SR)), min(n, int(release * SR))
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[n - r:] *= np.linspace(1, 0, r)
    return env


def render_atmosphere(plan: dict, tempo: float, total_samples: int, seed: int = 0) -> np.ndarray:
    """Render the planned layers into one stereo buffer (not normalised)."""
    spb = 60.0 / tempo
    bar = int(4 * spb * SR)
    curve = np.asarray(plan.get("energy_curve") or [0.5], np.float32)
    # per-sample energy, linear between bar centres
    centres = (np.arange(len(curve)) + 0.5) * bar
    energy = np.interp(np.arange(total_samples), centres, curve, left=curve[0], right=curve[-1]).astype(np.float32)
    v = _Voices(seed)
    out = np.zeros((total_samples, 2), np.float32)

    def add(x, start_s):
        a = max(0, start_s)
        b = min(total_samples, start_s + len(x))
        if b > a:
            out[a:b] += x[a - start_s:b - start_s]

    for layer in plan["layers"]:
        s0 = int(layer["start"] * spb * SR)
        n = int(layer["beats"] * spb * SR)
        kind, gain = layer["kind"], layer["gain"]
        if n <= 0 or s0 >= total_samples + 10 * SR:
            continue
        e = energy[min(s0, total_samples - 1):min(s0 + n, total_samples)]
        if len(e) < n:
            e = np.concatenate([e, np.full(n - len(e), e[-1] if len(e) else 0.3, np.float32)])
        if kind == "bed":
            if layer["style"] == "vinyl":
                hiss = _bp(v.noise(n), 1500, 7000) * 0.05
                clicks = np.zeros(n, np.float32)
                idx = v.rng.integers(0, n, size=max(1, int(n / SR * 9)))
                clicks[idx] = v.rng.uniform(0.2, 1.0, size=len(idx)).astype(np.float32)
                mono = hiss + _hp(clicks, 1200) * 0.6
            elif layer["style"] == "air":
                mono = _bp(v.noise(n), 2500, 9000) * 0.08
            else:
                mono = _lp(v.noise(n), 700) * 0.12
            x = np.stack([mono, np.roll(mono, int(0.011 * SR))], 1)
            x *= (0.5 + 0.8 * e)[:, None] * gain
        elif kind == "drone":
            raw = v.sines(layer["pitches"], n, detune=4, octave_mix=0.3) + 0.25 * v.saws(layer["pitches"][:2], n, 5)
            dark, bright = _lp(raw, 350), _lp(raw, 2200)
            mix = np.clip((e - 0.25) / 0.6, 0, 1)[:, None]            # brighter as the energy rises
            hand = np.linspace(1.0, 0.1, n, dtype=np.float32)[:, None] if layer.get("fade_out") else 1.0
            x = (dark * (1 - mix) + bright * mix) * hand * _fade(n, 1.5, 1.2)[:, None] * gain * (0.6 + 0.6 * e)[:, None]
        elif kind == "pad":
            if layer["style"] == "glass":
                raw = v.sines(layer["pitches"], n, detune=7, octave_mix=0.5)
            else:
                raw = _lp(v.saws(layer["pitches"], n, 10), 1800 if layer["style"] == "warm" else 900) * 0.8
            x = raw * _fade(n, 0.6, 0.8)[:, None] * gain * (0.5 + 0.6 * e)[:, None]
        elif kind == "shimmer":
            t = np.arange(n) / SR
            trem = (1 + 0.3 * np.sin(2 * np.pi * (1 / spb) * t))[:, None].astype(np.float32)
            raw = v.sines(layer["pitches"], n, detune=12, octave_mix=0.2) * trem
            ramp = np.linspace(0.15, 1.0, n, dtype=np.float32)[:, None] if layer.get("rise") else 1.0
            x = _hp(raw, 1500) * ramp * _fade(n, 0.3, 0.5)[:, None] * gain * (0.4 + 0.7 * e)[:, None]
        elif kind == "choir":
            src = v.saws(layer["pitches"], n, 14)
            t = np.arange(n) / SR
            src *= (1 + 0.004 * np.sin(2 * np.pi * 5.2 * t))[:, None]
            ah = _bp(src, 600, 900) + 0.6 * _bp(src, 1000, 1300) + 0.25 * _bp(src, 2400, 2900)   # "ah" formants
            x = ah * _fade(n, 0.5, 0.6)[:, None] * gain * 1.6 * (0.5 + 0.6 * e)[:, None]
        elif kind == "sparkle":
            x = np.zeros((n, 2), np.float32)
            step = int(0.5 * spb * SR)                               # eighth notes on the grid
            p = layer["pitches"]
            for k, pos in enumerate(range(0, n, step)):
                f = _hz(p[k % len(p)])
                m = min(int(0.6 * SR), n - pos)
                tt = np.arange(m) / SR
                bell = np.sin(2 * np.pi * f * tt + 1.2 * np.exp(-tt * 8) * np.sin(2 * np.pi * f * 3.5 * tt)) * np.exp(-tt * 6)
                pan = 0.25 if k % 2 else 0.75                          # ping-pong
                x[pos:pos + m, 0] += bell * (1 - pan)
                x[pos:pos + m, 1] += bell * pan
            x *= gain * (0.5 + 0.6 * e)[:, None]
        elif kind == "swell":
            chord = v.sines(layer["pitches"], n, detune=6, octave_mix=0.4) + 0.3 * _bp(v.noise(n), 800, 8000)[:, None]
            curve_up = np.linspace(0, 1, n, dtype=np.float32) ** 3       # reversed decay: rises into the downbeat
            x = chord * curve_up[:, None] * gain
        elif kind == "tail":
            x = v.sines(layer["pitches"], n, detune=5, octave_mix=0.3) * np.exp(-np.arange(n) / SR * 0.9)[:, None] * gain
        else:
            continue
        add(x.astype(np.float32), s0)

    ir = _reverb_ir(seconds=3.2, seed=seed + 5)
    wet = np.stack([oaconvolve(out[:, c], ir[:, c], mode="full")[:total_samples] for c in (0, 1)], 1)
    return (out * 0.6 + wet.astype(np.float32) * 0.7).astype(np.float32)
