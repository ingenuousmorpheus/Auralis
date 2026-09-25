"""Song Blueprint (AU-04): prompt + Artist DNA + R&B Atlas + voice → a song plan.

The blueprint is structured, editable and explained. It holds tempo, key,
meter, sections with bar counts, chords (Roman numerals plus the chord names
in the chosen key), arrangement per section, an energy curve and vocal-range
constraints. Every decision records *why* it was made. No audio and no
melody: melody is AU-05's job, and the originality rules forbid carrying
melody or lyrics over from any song.

Order of decisions (each one can be overridden by the user):

1. brief       what the words and explicit settings ask for (``brief.py``)
2. era         asked for, else the era that best fits tempo, mode and style
3. mode        asked for, else the words' mood, else the DNA's minor share
4. tempo       asked for, else DNA median moved into the era/feel band
5. form        lyrics headers, else R&B defaults shaped by DNA (intro bars,
               first-chorus time, chorus length, pre-chorus/bridge habits)
6. harmony     per section type, Atlas families and the artist's own loops
               ranked together (``artist_dna_weight``), under originality rules
7. key         chosen *last*: the voice range first, then DNA key families
8. groove, arrangement, energy and vocal registers follow from the above

``revise`` applies user edits and re-derives everything that depends on
them (chord names, timings, energy curve, vocal registers, checks), so an
edited blueprint is always consistent.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from ..theory import candidates as atlas_candidates
from ..theory import key_fit, load_atlas, suggest_keys
from ..theory.schema import is_roman
from ..generation.atmosphere import describe as describe_atmosphere
from ..generation.atmosphere import era_level
from .brief import parse_brief
from .chords import ChordError, key_name, note_name, parse_key, realise, split_progression
from .validation import SECTION_TYPES, validate_blueprint

BLUEPRINT_VERSION = 1
DEFAULT_LENGTH = 200                 # seconds, a typical R&B single
DEFAULT_VOICE = (48.0, 72.0)         # C3–C5 when there is no voice profile or DNA melody
ROLES = ["drums", "bass", "keys", "pad", "lead_vocal", "backing_vocals", "fx", "atmos"]
LABELS = {"intro": "Intro", "verse": "Verse", "pre-chorus": "Pre-chorus", "chorus": "Chorus",
          "bridge": "Bridge", "instrumental": "Interlude", "outro": "Outro"}
BASE_ENERGY = {"intro": 0.3, "verse": 0.45, "pre-chorus": 0.6, "chorus": 0.8, "bridge": 0.55,
               "instrumental": 0.5, "outro": 0.3}
FEEL_BANDS = {"slow": (60, 80), "mid": (80, 102), "fast": (100, 128)}

# Arrangement defaults. Editorial starting points, not Atlas research; the
# blueprint labels them that way. Levels: off / light / medium / full.
ARRANGEMENT = {
    "intro":        {"drums": "off", "bass": "off", "keys": "medium", "pad": "light", "lead_vocal": "off",
                     "backing_vocals": "off", "fx": "light"},
    "verse":        {"drums": "light", "bass": "medium", "keys": "medium", "pad": "light", "lead_vocal": "full",
                     "backing_vocals": "off", "fx": "off"},
    "pre-chorus":   {"drums": "medium", "bass": "medium", "keys": "medium", "pad": "medium", "lead_vocal": "full",
                     "backing_vocals": "light", "fx": "light"},
    "chorus":       {"drums": "full", "bass": "full", "keys": "full", "pad": "full", "lead_vocal": "full",
                     "backing_vocals": "full", "fx": "medium"},
    "bridge":       {"drums": "light", "bass": "medium", "keys": "full", "pad": "medium", "lead_vocal": "full",
                     "backing_vocals": "light", "fx": "light"},
    "instrumental": {"drums": "medium", "bass": "medium", "keys": "full", "pad": "medium", "lead_vocal": "off",
                     "backing_vocals": "off", "fx": "medium"},
    "outro":        {"drums": "light", "bass": "light", "keys": "medium", "pad": "medium", "lead_vocal": "light",
                     "backing_vocals": "light", "fx": "light"},
}
PALETTES = {
    "70s_soul": ["live drum kit", "electric bass", "Rhodes / organ", "rhythm guitar", "horns or strings"],
    "80s_quiet_storm": ["drum machine with a soft live snare", "synth or fretless bass", "DX-style electric piano",
                        "warm synth pads", "sax or guitar fills"],
    "90s_rnb": ["hip-hop drum programming", "sub bass", "Rhodes / piano", "string pads", "stacked background vocals"],
    "neo_soul": ["live-feel drums", "finger bass", "Rhodes", "guitar comping", "muted horns"],
    "2000s_rnb": ["programmed drums", "synth bass", "piano or keys loop", "pads", "vocal chops"],
    "modern_alt_rnb": ["sparse drums", "808 / sub bass", "ambient pads", "textures and resampled vocals",
                       "filtered keys"],
}
MIX_PROFILE = {"70s_soul": "warm-soul", "80s_quiet_storm": "warm-soul", "neo_soul": "warm-soul",
               "90s_rnb": "vocal-forward-rnb", "2000s_rnb": "vocal-forward-rnb",
               "modern_alt_rnb": "rhythmic-sparse"}
# Colour for the artist's own triad loops when they are used: the era's chord
# colours are applied, so a habit is re-voiced rather than copied.
_COLOUR_PREFS = {"major": ("maj9", "maj7"), "minor": ("min9", "min7"), "dominant": ("dom9", "dom13")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _round4(x: float, lo: int = 4, hi: int = 16) -> int:
    return int(max(lo, min(hi, 4 * round(x / 4))))


# ─── Decisions ──────────────────────────────────────────────────────────────

def _choose_era(brief, dna, atlas, tempo_hint):
    if brief["era"]:
        how = "you chose it" if "era" in brief["set_by_you"] else f"your prompt said “{_heard(brief, 'era')}”"
        return brief["era"], [f"{_era_name(atlas, brief['era'])}: {how}."]
    scores = []
    for e in atlas["eras"]:
        s, why = 0.0, []
        lo, hi = e["bpm_band"]
        if tempo_hint and lo <= tempo_hint <= hi:
            s += 1.0
            why.append(f"{round(tempo_hint)} BPM sits in its {lo}–{hi} BPM band")
        if brief["mode"]:
            share = _mode_share(atlas, e["id"], brief["mode"])
            s += share
            if share >= 0.3:
                why.append(f"it has {brief['mode']}-key progression families")
        for field in ("vocal", "groove"):
            if brief[field] and brief[field] in e[field]:
                s += 0.5
                why.append(f"{brief[field].replace('_', ' ')} is typical of it")
        if brief["harmony"] and any(brief["harmony"] in p["harmony_colors"] and p["eras"].get(e["id"])
                                    for p in atlas["progression_families"]):
            s += 0.3
        scores.append((s, e["id"], why))
    scores.sort(key=lambda t: (-t[0], t[1]))
    s, era, why = scores[0]
    return era, [f"{_era_name(atlas, era)} fits best: " + ("; ".join(why) if why else "a neutral default") +
                 ". Pick another era in Era & style to change it."]


def _mode_share(atlas, era, mode):
    fams = [p for p in atlas["progression_families"] if p["eras"].get(era)]
    return sum(p["mode"] == mode for p in fams) / len(fams) if fams else 0.0


def _choose_mode(brief, dna, atlas):
    if brief["key"]:
        return brief["key"]["mode"], [f"{brief['key']['mode'].capitalize()}: the key you asked for."]
    if brief["mode"]:
        how = "you chose it" if "mode" in brief["set_by_you"] else f"your prompt said “{_heard(brief, 'mode')}”"
        return brief["mode"], [f"{brief['mode'].capitalize()}: {how}."]
    key = (dna or {}).get("traits", {}).get("key")
    if key:
        share = key["minor_share"]
        mode = "minor" if share >= 0.5 else "major"
        other = "major" if mode == "minor" else "minor"
        if brief["era"] and _mode_share(atlas, brief["era"], mode) == 0 and _mode_share(atlas, brief["era"], other):
            return other, [f"{other.capitalize()}: most of your songs are {mode}, but every "
                           f"{_era_name(atlas, brief['era'])} family in the Atlas is {other}."]
        return mode, [f"{mode.capitalize()}: {round((share if mode == 'minor' else 1 - share) * 100)}% "
                      f"of your songs are in {mode} keys (Artist DNA)."]
    return "minor", ["Minor: no mood words and no Artist DNA, so the most common R&B choice."]


def _choose_tempo(brief, dna, era_row):
    if brief["tempo"]:
        how = "you set it" if "tempo" in brief["set_by_you"] else f"your prompt said “{_heard(brief, 'tempo')}”"
        return float(brief["tempo"]), [f"{brief['tempo']} BPM: {how}."]
    lo, hi = era_row["bpm_band"]
    why = []
    if brief["tempo_feel"]:
        flo, fhi = FEEL_BANDS[brief["tempo_feel"]]
        if max(lo, flo) < min(hi, fhi):
            lo, hi = max(lo, flo), min(hi, fhi)
        else:
            lo, hi = flo, fhi
        why.append(f"“{_heard(brief, 'tempo_feel')}” means {lo}–{hi} BPM")
    else:
        why.append(f"{era_row['name']} usually sits at {lo}–{hi} BPM")
    tempo = (dna or {}).get("traits", {}).get("tempo")
    if tempo:
        med = tempo["median"]
        options = [(0, med, f"your songs centre on {med:.0f} BPM")]
        if not lo <= med <= hi:
            for f, word in ((0.5, "half"), (2.0, "double")):
                if lo <= med * f <= hi:
                    options.append((0, med * f, f"your songs centre on {med:.0f} BPM; {word}-time of that "
                                                f"is {med * f:.0f}"))
        inside = [o for o in options if lo <= o[1] <= hi]
        if inside:
            bpm, reason = inside[-1][1], inside[-1][2]
        else:
            bpm = min(max(med, lo), hi)
            reason = f"your songs centre on {med:.0f} BPM, moved to the nearest edge of that band"
        why.append(reason)
    else:
        bpm = (lo + hi) / 2
        why.append("no Artist DNA, so the middle of the band")
    return float(round(bpm)), ["; ".join(why) + "."]


def _choose_form(brief, dna, tempo):
    """Section list [(type, bars)] plus reasons."""
    form = (dna or {}).get("traits", {}).get("form") or {}
    bar_s = 240.0 / tempo
    why = []
    if brief["lyric_sections"] and any(b["type"] for b in brief["lyric_sections"]):
        order = [b["type"] or "verse" for b in brief["lyric_sections"]]
        if order[0] != "intro":
            order.insert(0, "intro")
        if order[-1] != "outro":
            order.append("outro")
        why.append("Section order follows the headers in your lyrics.")
    else:
        forms = form.get("common_forms") or []
        total = sum(f["weight"] for f in forms) or 1
        pc_share = sum(f["weight"] for f in forms if "PC" in f["form"].split()) / total if forms else 0.6
        br_share = sum(f["weight"] for f in forms if "B" in f["form"].split()) / total if forms else 0.6
        use_pc = pc_share >= 0.4
        use_bridge = brief["bridge"] if brief["bridge"] is not None else br_share >= 0.3
        order = ["intro", "verse"] + (["pre-chorus"] if use_pc else []) + ["chorus", "verse"] + \
            (["pre-chorus"] if use_pc else []) + ["chorus"] + (["bridge"] if use_bridge else []) + \
            ["chorus", "outro"]
        if forms:
            why.append(f"{'Pre-choruses' if use_pc else 'No pre-chorus'}: {'' if use_pc else 'only '}"
                       f"{round(pc_share * 100)}% of your chorus-bearing forms have one.")
        if brief["bridge"] is not None:
            why.append(f"{'A bridge' if use_bridge else 'No bridge'}: your prompt said “{_heard(brief, 'bridge')}”.")
        elif forms:
            why.append(f"{'A bridge' if use_bridge else 'No bridge'}: {round(br_share * 100)}% of your forms have one.")
        else:
            why.append("Standard R&B form: verse, pre-chorus, chorus twice, bridge, final chorus.")

    intro = _round4(form.get("intro_bars") or 4, 4, 8)
    chorus = _round4((form.get("section_bars") or {}).get("chorus", 8), 8, 16)
    pc = _round4((form.get("section_bars") or {}).get("pre-chorus", 4), 4, 8)
    if brief["chorus_emphasis"]:
        chorus = max(chorus, 8)
    verse = 16 if tempo < 80 else 8 if tempo >= 115 else 12
    fc = form.get("first_chorus_seconds")
    if fc:
        before = fc / bar_s
        verse = _round4(before - intro - (pc if "pre-chorus" in order else 0), 8, 16)
        why.append(f"First chorus near {_fmt_s(fc)} like your songs: {intro}-bar intro, {verse}-bar verse "
                   f"(your intros are about {round(form.get('intro_bars') or intro)} bars).")
    bars = {"intro": intro, "verse": verse, "pre-chorus": pc, "chorus": chorus, "bridge": 8,
            "instrumental": 8, "outro": 4 if tempo < 90 else 8}
    sections = [[t, bars[t]] for t in order]

    # Lyrics decide a verse's length when they are longer than the default.
    if brief["lyric_sections"]:
        typed = [b for b in brief["lyric_sections"] if b["type"]]
        idx = [i for i, (t, _) in enumerate(sections) if t not in ("intro", "outro")]
        for i, block in zip(idx, typed):
            need = _round4(len(block["lines"]) * 2, 4, 16)       # about two bars per sung line
            if need > sections[i][1]:
                sections[i][1] = need

    target = brief["length_seconds"] or DEFAULT_LENGTH
    dur = lambda: sum(b for _, b in sections) * bar_s
    if dur() < target - 20:
        sections[-2][1] = min(16, sections[-2][1] * 2)             # double the last chorus
        why.append("The last chorus is doubled to reach the length.")
    while dur() > target + 25 and any(t == "verse" and b > 8 for t, b in sections):
        i = max(i for i, (t, b) in enumerate(sections) if t == "verse" and b > 8)
        sections[i][1] -= 4
    if dur() > target + 25 and "bridge" in [t for t, _ in sections] and brief["bridge"] is not True:
        sections = [s for s in sections if s[0] != "bridge"]
        why.append("The bridge is dropped to keep the length.")
    if brief["length_seconds"]:
        why.append(f"Aiming for about {_fmt_s(target)} "
                   f"({'your prompt said “' + _heard(brief, 'length_seconds') + '”' if 'length_seconds' not in brief['set_by_you'] else 'you set it'}).")
    return sections, why


def _dna_loops(dna, mode):
    loops = ((dna or {}).get("traits", {}).get("harmony", {}).get("loops") or {}).get(mode) or []
    out = []
    for loop in loops:
        roman = split_progression(loop["progression"])
        if len(roman) >= 2 and all(is_roman(t) for t in roman):
            out.append({"roman": roman, "weight": loop["weight"]})
    return out


def _colour(roman: list[str], era_colors: list[str]) -> list[str]:
    """Re-voice the artist's triad loop with the era's chord colours."""
    have = set(era_colors)

    def pick(kind):
        return next((c for c in _COLOUR_PREFS[kind] if c in have), None)

    out = []
    for t in roman:
        base = t
        if any(ch.isdigit() for ch in t) or "/" in t:
            out.append(t)
            continue
        numeral = t.lstrip("♭♯")
        if numeral.islower():
            c = pick("minor")
            out.append(base + ({"min9": "9", "min7": "7"}.get(c, "")))
        elif numeral == "V":
            c = pick("dominant")
            out.append(base + ({"dom9": "9", "dom13": "13"}.get(c, "7")))
        else:
            c = pick("major")
            out.append(base + ({"maj9": "maj9", "maj7": "maj7"}.get(c, "")))
    return out


def _harmony_options(sec_type, mode, brief, era, atlas, dna, weight, voice_range, families):
    """Ranked progression options for one section type, Atlas and DNA together."""
    res = atlas_candidates(era, section=sec_type, harmony=brief["harmony"], n=12,
                           voice_range=voice_range, dna_key_families=families, atlas=atlas)
    options = []
    for h in res["harmony"]:
        if h["mode"] != mode:
            continue
        s = h["era_affinity"] + (0.3 if sec_type in h["sections"] else 0) + \
            (0.4 if brief["harmony"] and brief["harmony"] in h.get("harmony_colors", []) else 0)
        options.append({"roman": h["roman"], "name": h["name"], "source": f"atlas:{h['id']}",
                        "status": h["status"], "sources": h["sources"], "loop": h["loop"],
                        "score": s * (1 - weight), "why": f"R&B Atlas “{h['name']}” ({h['status']}): {h['comment']}"})
    fallback = not options
    in_era = {o["source"] for o in options}
    src = {x["id"]: x for x in atlas["sources"]}
    for p in atlas["progression_families"]:     # other eras' families in this mode, ranked lower
        if p["mode"] != mode or f"atlas:{p['id']}" in in_era:
            continue
        s = (max(p["eras"].values()) * 0.5 + (0.3 if sec_type in p["sections"] else 0)) * (0.8 if fallback else 0.5)
        options.append({"roman": p["roman"], "name": p["name"], "source": f"atlas:{p['id']}",
                        "status": p["status"],
                        "sources": [{"id": i, "title": src[i]["title"], "url": src[i]["url"]} for i in p["sources"]],
                        "loop": p["loop"], "score": s * (1 - weight), "borrowed": True,
                        "why": f"R&B Atlas “{p['name']}” ({p['status']}), borrowed from another era"
                               f"{': this era has no ' + mode + '-key family' if fallback else ''}. {p['comment']}"})
    loops = _dna_loops(dna, mode)
    if loops:
        top = max(l["weight"] for l in loops)
        era_colors = next(e for e in atlas["eras"] if e["id"] == era)["chord_colors"]
        for rank, loop in enumerate(loops):
            coloured = _colour(loop["roman"], era_colors)
            options.append({"roman": coloured, "name": "From your songs", "source": "dna",
                            "dna_loop": " – ".join(loop["roman"]), "status": "your catalog", "sources": [],
                            "loop": True, "score": (loop["weight"] / top) * 1.3 * weight - 0.05 * rank,
                            "why": f"Your own loop {' – '.join(loop['roman'])} (Artist DNA), re-voiced with "
                                   f"{_era_name(atlas, era)} chord colours."})
    seen, ranked = set(), []
    for o in sorted(options, key=lambda o: -o["score"]):
        k = " ".join(o["roman"])
        if k not in seen:
            seen.add(k)
            ranked.append({**o, "score": round(o["score"], 3)})
    return ranked, fallback


def _assign_harmony(sections, options_by_type, seed):
    """Pick one option per section type under the originality rules:
    at most one section type uses a loop from the artist's catalog, and the
    chorus never repeats the verse's progression."""
    chosen, dna_used, why = {}, None, {}
    order = sorted(options_by_type, key=lambda t: ["chorus", "verse", "pre-chorus", "bridge", "intro",
                                                    "outro", "instrumental"].index(t))
    for t in order:
        opts = options_by_type[t]
        if not opts:
            continue
        start = seed % len(opts) if seed else 0
        rotated = opts[start:] + opts[:start]
        used = [c["roman"] for c in chosen.values()]
        allowed = [o for o in rotated if not (o["source"] == "dna" and dna_used and dna_used != t)]
        # prefer a progression no other section type has; the chorus must differ from the verse
        pick = next((o for o in allowed if o["roman"] not in used), None) or             next((o for o in allowed if not (t in ("verse", "pre-chorus") and "chorus" in chosen
                                             and o["roman"] == chosen["chorus"]["roman"])), None)
        pick = pick or rotated[0]
        if pick["source"] == "dna":
            dna_used = t
        chosen[t] = pick
    return chosen


def _chords_per_bar(sec_type, option, lift_id, dna):
    if len(option["roman"]) == 2 and option.get("loop") and sec_type in ("intro", "verse", "outro"):
        return 0.5, "Two chords over two bars each: slow harmonic rhythm keeps the verse spacious."
    if sec_type == "pre-chorus" and lift_id == "harmonic_rhythm_lift":
        return 2.0, "Two chords a bar: faster harmonic rhythm lifts into the chorus (Atlas section lift)."
    rate = (dna or {}).get("traits", {}).get("harmony", {}).get("changes_per_bar")
    if sec_type == "chorus" and rate and rate >= 1.75:
        return 2.0, f"Two chords a bar, matching your {rate:.1f} changes per bar."
    return 1.0, "One chord a bar" + (f" (your songs change about {rate:.1f} times a bar)." if rate else ".")


# ─── Build ─────────────────────────────────────────────────────────────────

def build_blueprint(prompt: str = "", lyrics: str = "", *, dna: dict | None = None,
                    voice_range: tuple[float, float] | None = None, voice_name: str | None = None,
                    catalog: list[dict] | None = None, artist_dna_weight: float = 0.5, seed: int = 0,
                    atlas: dict | None = None, **settings) -> dict:
    """Create a complete, explained blueprint. ``settings`` are explicit choices
    (era, harmony, vocal, groove, key, tempo, length_seconds, bridge)."""
    atlas = atlas or load_atlas()
    brief = parse_brief(prompt, lyrics, **settings)
    weight = max(0.0, min(1.0, float(artist_dna_weight))) if dna and not dna.get("empty") else 0.0
    dna = dna if weight > 0 else None
    why: dict[str, list[str]] = {}

    mode, why["mode"] = _choose_mode(brief, dna, atlas)
    brief = {**brief, "mode": mode}
    dna_tempo = (dna or {}).get("traits", {}).get("tempo", {}).get("median")
    era, why["era"] = _choose_era(brief, dna, atlas, brief["tempo"] or dna_tempo)
    era_row = next(e for e in atlas["eras"] if e["id"] == era)
    tempo, why["tempo"] = _choose_tempo(brief, dna, era_row)

    vr, vsource = _voice_range(voice_range, voice_name, dna)
    families = [f["major_tonic"] for f in (dna or {}).get("traits", {}).get("key", {}).get("families", [])] or None

    # Key last: voice first, then the artist's key families.
    if brief["key"]:
        tonic = brief["key"]["tonic"]
        fit = next(k for k in suggest_keys(mode, vr, families, n=12) if k["tonic"] == tonic)
        how = "you set it" if "key" in brief["set_by_you"] else f"your prompt said “{_heard(brief, 'key')}”"
        why["key"] = [f"{key_name(tonic, mode)}: {how}. Voice check: {fit['why']}."]
    else:
        best = suggest_keys(mode, vr, families, n=1)[0]
        tonic = best["tonic"]
        why["key"] = [f"{key_name(tonic, mode)}: {best['why']}."]

    form, why["form"] = _choose_form(brief, dna, tempo)
    lifts = [l for l in atlas["section_lift"] if era in l["eras"]]
    lift = lifts[0] if lifts else None
    types = sorted({t for t, _ in form})
    options = {}
    fallback_types = []
    for t in types:
        opts, fb = _harmony_options(t, mode, brief, era, atlas, dna, weight, vr, families)
        options[t] = opts
        if fb:
            fallback_types.append(t)
    chosen = _assign_harmony(form, options, seed)

    lyric_blocks = [b for b in brief["lyric_sections"]]
    typed_blocks = [b for b in lyric_blocks if b["type"]]
    untyped = [b for b in lyric_blocks if not b["type"]]
    sections = []
    counters: dict[str, int] = {}
    block_iter = iter(typed_blocks)
    for t, bars in form:
        counters[t] = counters.get(t, 0) + 1
        opt = chosen.get(t) or {"roman": ["i" if mode == "minor" else "I"], "name": "Tonic", "source": "default",
                                "status": "default", "sources": [], "why": "No option found."}
        rate, rate_why = _chords_per_bar(t, opt, lift["id"] if lift else None, dna)
        lines = []
        if t not in ("intro", "outro"):
            if typed_blocks:
                block = next(block_iter, None)
                lines = block["lines"] if block else []
            elif untyped and t == "verse" and counters[t] == 1:
                lines = untyped[0]["lines"]
        energy = BASE_ENERGY[t]
        sections.append({
            "id": uuid.uuid4().hex[:8], "type": t,
            "label": LABELS[t] + (f" {counters[t]}" if t in ("verse", "chorus", "pre-chorus") else ""),
            "bars": int(bars), "energy": energy, "chords_per_bar": rate,
            "progression": {k: opt.get(k) for k in ("roman", "name", "source", "status", "sources", "dna_loop")
                            if opt.get(k) is not None},
            "arrangement": dict(ARRANGEMENT[t], atmos=era_level(t, era)),
            "lyrics": lines,
            "why": [opt["why"], rate_why],
        })

    # Energy: the verse sets the floor, choruses lift by the artist's own lift.
    dlift = (dna or {}).get("traits", {}).get("form", {}).get("chorus_lift")
    chorus_e = min(0.95, BASE_ENERGY["verse"] + max(0.25, dlift or 0) + (0.1 if brief["chorus_emphasis"] else 0))
    last_chorus = max((i for i, s in enumerate(sections) if s["type"] == "chorus"), default=None)
    for i, s in enumerate(sections):
        if s["type"] == "chorus":
            s["energy"] = round(min(1.0, chorus_e + (0.07 if i == last_chorus else 0)), 2)
        elif s["type"] == "verse" and s["label"].endswith("2"):
            s["energy"] = round(s["energy"] + 0.05, 2)
    why["energy"] = [f"Choruses sit {round((chorus_e - BASE_ENERGY['verse']) * 100)} points above the verses"
                     + (f" (your choruses lift about {round(dlift * 100)} points)" if dlift else "")
                     + ("; “big chorus” adds more" if brief["chorus_emphasis"] else "")
                     + "; the final chorus peaks."]

    # Groove: Atlas profile for the era that holds this tempo.
    grooves = [g for g in atlas["grooves"] if era in g["eras"]]
    fits = [g for g in grooves if g["bpm_band"][0] <= tempo <= g["bpm_band"][1]] or grooves or atlas["grooves"]
    if brief["groove"]:
        fits.sort(key=lambda g: g["feel"] != brief["groove"])
    g = fits[0]
    src = {s["id"]: s for s in atlas["sources"]}
    groove = {k: g[k] for k in ("id", "name", "feel", "swing_ratio", "offsets_ms", "quantize_strength",
                                "push_pull", "pocket_width_ms", "status")}
    groove["sources"] = [{"id": i, "title": src[i]["title"], "url": src[i]["url"]} for i in g["sources"]]
    gw = [f"{g['name']} ({g['status']}) from the R&B Atlas: {g['push_pull']}."]
    dg = (dna or {}).get("traits", {}).get("groove")
    if dg:
        groove["syncopation"] = dg["syncopation"]
        gw.append(f"Keep syncopation near yours: {round(dg['syncopation'] * 100)}% of your drum hits land off the beat.")
    why["groove"] = gw

    prod = (dna or {}).get("traits", {}).get("production") or {}
    arrangement = {
        "palette": PALETTES[era], "palette_status": "editorial default, not Atlas research",
        "mix_profile": MIX_PROFILE[era],
        "section_lift": ({"id": lift["id"], "name": lift["name"], "changes": lift["changes"], "status": lift["status"]}
                         if lift else None),
        "comments": [],
    }
    if prod.get("low_ratio") is not None:
        arrangement["comments"].append(f"Low end carries the record: {round(prod['low_ratio'] * 100)}% of your energy "
                                    f"sits below 250 Hz.")
    if prod.get("stereo_width") is not None:
        arrangement["comments"].append(f"Your mixes are {'narrow' if prod['stereo_width'] < 0.3 else 'wide'} "
                                    f"(width {prod['stereo_width']:.2f}); open the stereo image in choruses.")
    atmosphere = describe_atmosphere(era, dna)
    why["atmosphere"] = atmosphere["why"] + [
        "Each section's Atmos level (off / light / medium / full) sets how much texture it gets; "
        "the layers follow its chords and the energy curve."]
    why["arrangement"] = [f"{_era_name(atlas, era)} palette; roles per section follow energy"
                          + (f" and the Atlas “{lift['name']}” lift ({', '.join(lift['changes'])})" if lift else "")
                          + ". Choruses bring in backing vocals, as your stem sets do."]

    vocal_patterns = atlas_candidates(era, vocal=brief["vocal"], n=6, atlas=atlas)["vocal"]
    bp = {
        "blueprint_version": BLUEPRINT_VERSION,
        "id": uuid.uuid4().hex[:12],
        "revision": 1,
        "created_at": _now(), "updated_at": _now(),
        "title": _title(prompt),
        "brief": {k: brief[k] for k in ("prompt", "heard", "set_by_you", "harmony", "vocal", "groove",
                                         "tempo_feel", "length_seconds", "chorus_emphasis")},
        "lyrics": brief["lyrics"],
        "inputs": {"artist_dna_weight": weight, "seed": seed, "used_dna": bool(dna),
                   "dna_songs": (dna or {}).get("method", {}).get("songs_used")},
        "era": {"id": era, "name": era_row["name"], "status": era_row["status"],
                "harmonic_rhythm": era_row["harmonic_rhythm"]},
        "tempo": tempo, "meter": "4/4", "key": key_name(tonic, mode),
        "groove": groove,
        "sections": sections,
        "harmony_options": {t: o[:6] for t, o in options.items()},
        "arrangement": arrangement,
        "atmosphere": atmosphere,
        "vocal": {"range_low_midi": vr[0], "range_high_midi": vr[1], "range_source": vsource,
                  "patterns": {p["section"]: {k: p[k] for k in ("id", "name", "contour", "start_degree",
                                                                 "end_degree", "peak_degree", "phrase_bars",
                                                                 "syncopation", "melisma", "status")}
                               for p in reversed(vocal_patterns)}},
        "why": why,
        "edited": [],
    }
    if fallback_types:
        why["harmony"] = [f"{era_row['name']} has no {mode}-key family in the Atlas, so "
                          f"{', '.join(fallback_types)} borrow from other eras."]
    return _derive(bp, catalog=catalog, first=True)


# ─── Revise ─────────────────────────────────────────────────────────────────

EDITABLE = ("title", "tempo", "key", "sections", "lyrics")
SECTION_FIELDS = ("type", "bars", "energy", "chords_per_bar", "arrangement", "lyrics", "renderer")


def revise(blueprint: dict, changes: dict, catalog: list[dict] | None = None) -> dict:
    """Apply user edits and re-derive everything that depends on them."""
    bp = copy.deepcopy(blueprint)
    edited = set(bp.get("edited", []))
    for field in EDITABLE:
        if field not in changes or field == "sections":
            continue
        if changes[field] != bp.get(field):
            bp[field] = changes[field]
            edited.add(field)
            if field in ("tempo", "key"):
                bp["why"][field] = [f"You set {changes[field]}{' BPM' if field == 'tempo' else ''}."] + \
                    [w for w in bp["why"].get(field, []) if not w.startswith("You set")][:1]
    if "sections" in changes:
        old = {s["id"]: s for s in bp["sections"]}
        new_sections = []
        counters: dict[str, int] = {}
        for raw in changes["sections"]:
            prev = old.get(raw.get("id"))
            s = copy.deepcopy(prev) if prev else {
                "id": uuid.uuid4().hex[:8], "type": raw.get("type", "verse"), "bars": 8,
                "energy": BASE_ENERGY.get(raw.get("type", "verse"), 0.5), "chords_per_bar": 1.0,
                "arrangement": dict(ARRANGEMENT.get(raw.get("type", "verse"), ARRANGEMENT["verse"]),
                                    atmos=era_level(raw.get("type", "verse"), (bp.get("era") or {}).get("id", ""))),
                "lyrics": [], "why": ["You added this section."],
                "progression": _default_progression(bp, raw.get("type", "verse")),
            }
            for f in SECTION_FIELDS:
                if f in raw:
                    s[f] = raw[f]
            if "progression" in raw:
                roman = raw["progression"].get("roman") if isinstance(raw["progression"], dict) else raw["progression"]
                if isinstance(roman, str):
                    roman = split_progression(roman)
                picked = raw["progression"] if isinstance(raw["progression"], dict) else {}
                if roman != s["progression"].get("roman"):
                    if picked.get("source") and picked.get("source") != "edited":
                        s["progression"] = {k: picked[k] for k in ("roman", "name", "source", "status", "sources",
                                                                    "dna_loop") if k in picked}
                        s["why"] = [picked.get("why", "You picked this option.")] + s["why"][1:]
                    else:
                        s["progression"] = {"roman": roman, "name": "Your chords", "source": "edited",
                                            "status": "edited", "sources": []}
                        s["why"] = ["You edited these chords."] + s["why"][1:]
            counters[s["type"]] = counters.get(s["type"], 0) + 1
            s["label"] = LABELS.get(s["type"], s["type"].title()) + (
                f" {counters[s['type']]}" if s["type"] in ("verse", "chorus", "pre-chorus") else "")
            new_sections.append(s)
        bp["sections"] = new_sections
        edited.add("sections")
    bp["edited"] = sorted(edited)
    bp["revision"] = int(bp.get("revision", 1)) + 1
    bp["updated_at"] = _now()
    return _derive(bp, catalog=catalog)


def regenerate(blueprint: dict, section_id: str, catalog: list[dict] | None = None) -> dict:
    """New chords for one section (and the other sections of its type, so the
    choruses stay the same as each other). Everything else is kept."""
    bp = copy.deepcopy(blueprint)
    target = next((s for s in bp["sections"] if s["id"] == section_id), None)
    if target is None:
        raise KeyError(f"Unknown section: {section_id}")
    opts = bp.get("harmony_options", {}).get(target["type"]) or []
    if not opts:
        raise ValueError(f"No other harmony options for a {target['type']}.")
    current = target["progression"].get("roman")
    idx = next((i for i, o in enumerate(opts) if o["roman"] == current), -1)
    others = [s for s in bp["sections"] if s["type"] != target["type"]]
    other_dna = any(s["progression"].get("source") == "dna" for s in others)
    taken = [s["progression"].get("roman") for s in others]
    ordered = [opts[(idx + step) % len(opts)] for step in range(1, len(opts) + 1)]
    ordered = [o for o in ordered if not (o["source"] == "dna" and other_dna)] or ordered
    pick = next((o for o in ordered if o["roman"] != current and o["roman"] not in taken), None) or         next((o for o in ordered if o["roman"] != current), ordered[0])
    changes = {"sections": [
        {"id": s["id"], "progression": pick} if s["type"] == target["type"] else {"id": s["id"]}
        for s in bp["sections"]]}
    return revise(bp, changes, catalog=catalog)


# ─── Derived fields ────────────────────────────────────────────────────────

def _derive(bp: dict, catalog=None, first=False) -> dict:
    try:
        tonic, mode = parse_key(bp["key"])
        bp["key"] = key_name(tonic, mode)
    except ChordError:
        tonic, mode = None, None
    bp["key_tonic"], bp["mode"] = tonic, mode
    tempo = float(bp.get("tempo") or 0)
    bar_s = 240.0 / tempo if tempo > 0 else 0.0
    vr = (bp["vocal"]["range_low_midi"], bp["vocal"]["range_high_midi"])
    t_midi = key_fit(tonic, vr)[2] if tonic is not None else None

    bar = 0
    curve = []
    for i, s in enumerate(bp["sections"]):
        s["start_bar"] = bar + 1
        s["start_seconds"] = round(bar * bar_s, 2)
        bars = int(s.get("bars") or 0)
        s["chords"] = _lay_chords(s, tonic, mode)
        # energy curve: flat, pre-choruses ramp towards the next section, outros fade
        nxt = bp["sections"][i + 1]["energy"] if i + 1 < len(bp["sections"]) else None
        for b in range(bars):
            e = s["energy"]
            if s["type"] == "pre-chorus" and nxt is not None and bars > 1:
                e = s["energy"] + (nxt - 0.05 - s["energy"]) * b / (bars - 1)
            elif s["type"] == "outro" and bars > 1:
                e = s["energy"] * (1 - 0.6 * b / (bars - 1))
            curve.append(round(max(0.0, min(1.0, e)), 3))
        s["vocal"] = _section_vocal(s, t_midi, vr, bp)
        bar += bars
    bp["total_bars"] = bar
    bp["duration_seconds"] = round(bar * bar_s, 1)
    bp["energy_curve"] = curve

    peaks = {s["type"]: s["vocal"]["peak_midi"] for s in bp["sections"] if s["vocal"]}
    if "verse" in peaks and "chorus" in peaks:
        bp["vocal"]["lift_semitones"] = round(peaks["chorus"] - peaks["verse"])
    bp["vocal"]["tonic_midi"] = t_midi
    bp["vocal"]["range"] = f"{note_name(vr[0])}–{note_name(vr[1])}"
    bp["vocal"]["why"] = [
        f"Registers are placed inside {bp['vocal']['range']} ({bp['vocal']['range_source']}), a semitone "
        f"below your top note: verses low-middle, pre-choruses climbing, choruses up to about an octave above "
        f"the tonic" + (f", a lift of {bp['vocal']['lift_semitones']} semitones over the verse peak."
                        if "lift_semitones" in bp["vocal"] else ".")]
    bp["originality"] = _originality(bp, catalog, first)
    bp["validation"] = validate_blueprint(bp)
    return bp


def _lay_chords(s, tonic, mode):
    roman = s.get("progression", {}).get("roman") or []
    rate = float(s.get("chords_per_bar") or 1)
    bars = int(s.get("bars") or 0)
    if not roman or bars <= 0 or tonic is None:
        return []
    beats_each = 4.0 / rate
    total = bars * 4
    out, pos, i = [], 0.0, 0
    while pos < total - 1e-6:
        token = roman[i % len(roman)]
        try:
            name = realise(token, tonic, mode)
        except ChordError:
            name = "?"
        length = min(beats_each, total - pos)
        out.append({"bar": int(pos // 4) + 1, "beat": int(pos % 4) + 1, "beats": length,
                    "roman": token, "chord": name})
        pos += length
        i += 1
    return out


def _section_vocal(s, t, vr, bp):
    if t is None or s["arrangement"].get("lead_vocal", "off") == "off":
        return None
    low, high = vr
    top = high - 1
    plan = {"verse": (-5, 7, 5), "pre-chorus": (-2, 9, 9), "chorus": (0, 12, 12), "bridge": (0, 14, 14),
            "instrumental": (0, 12, 9), "intro": (0, 12, 9), "outro": (-2, 12, 9)}
    lo_off, hi_off, peak_off = plan.get(s["type"], (-5, 12, 9))
    if s["type"] == "chorus" and bp.get("brief", {}).get("chorus_emphasis") and t + 14 <= top:
        hi_off = peak_off = 14
    lo_n = max(low, t + lo_off)
    hi_n = min(top, t + hi_off)
    peak = min(top, t + peak_off)
    if hi_n < lo_n:
        hi_n = lo_n
    pattern = bp["vocal"].get("patterns", {}).get(s["type"]) or \
        (bp["vocal"].get("patterns", {}).get("chorus") if s["type"] in ("bridge", "outro") else None)
    return {"low_midi": lo_n, "high_midi": hi_n, "peak_midi": peak,
            "low": note_name(lo_n), "high": note_name(hi_n), "peak": note_name(peak),
            "pattern": pattern["name"] if pattern else None,
            "lines": len(s.get("lyrics") or [])}


def _originality(bp, catalog, first):
    checks = [{"id": "no_copied_material", "status": "pass",
               "label": "No melody, lyrics or audio from any song",
               "detail": "The blueprint holds Roman numerals, bar counts and vocal ranges only. "
                         "Melody is written later and must be new."}]
    dna_secs = [s["label"] for s in bp["sections"] if s["progression"].get("source") == "dna"]
    dna_types = {s["type"] for s in bp["sections"] if s["progression"].get("source") == "dna"}
    checks.append({"id": "catalog_loops", "status": "pass" if len(dna_types) <= 1 else "flag",
                   "label": "Your own chord loops are used in at most one section type",
                   "detail": (f"Your loop is re-voiced in: {', '.join(dna_secs)}." if dna_secs
                              else "No loop is taken from your catalog.") +
                             (" More than one section type now uses your loops; consider varying one."
                              if len(dna_types) > 1 else "")})
    prog = {s["type"]: s["progression"].get("roman") for s in bp["sections"]}
    if "verse" in prog and "chorus" in prog:
        same = prog["verse"] == prog["chorus"]
        checks.append({"id": "contrast", "status": "flag" if same else "pass",
                       "label": "The chorus has its own chords",
                       "detail": "Verse and chorus share a progression; lift will rely on arrangement alone."
                                 if same else "Verse and chorus use different progressions."})
    if catalog and bp.get("key") and bp.get("tempo"):
        form = " ".join(_SHORT.get(s["type"], "?") for s in bp["sections"])
        here = (bp.get("key_tonic"), bp.get("mode"))
        hits = [c for c in catalog if c.get("bpm") and abs(float(c["bpm"]) - float(bp["tempo"])) <= 2
                and _same_key(c.get("key"), here)]
        twin = [c for c in hits if c.get("form") == form]
        if twin:
            checks.append({"id": "catalog_twin", "status": "flag",
                           "label": "Tempo, key and form differ from each of your songs",
                           "detail": f"Same tempo (±2 BPM), key and form as {len(twin)} of your songs. "
                                     "Change one of them to keep this song distinct."})
        else:
            checks.append({"id": "catalog_twin", "status": "pass" if not hits else "info",
                           "label": "Tempo, key and form differ from each of your songs",
                           "detail": (f"{len(hits)} of your songs share this tempo and key, but not the form."
                                      if hits else "No song of yours shares this tempo and key.")})
    if catalog and any(c.get("roman_per_bar") for c in catalog):
        from ..artist.similarity import harmony_check

        h = harmony_check(bp, [c for c in catalog if c.get("roman_per_bar")])
        checks.append({k: h[k] for k in ("id", "label", "status", "detail")})
    return {"checks": checks,
            "note": "Chords are compared with every song you've switched on. The melody is compared with "
                    "your lead vocals after rendering (Check originality); audio is not compared."}


_SHORT = {"intro": "Intro", "verse": "V", "pre-chorus": "PC", "chorus": "C", "bridge": "B",
          "instrumental": "Inst", "outro": "Outro"}


def _same_key(text, here):
    try:
        return parse_key(text or "") == here
    except ChordError:
        return False


def _default_progression(bp, sec_type):
    opts = bp.get("harmony_options", {}).get(sec_type) or bp.get("harmony_options", {}).get("verse") or []
    if opts:
        o = opts[0]
        return {k: o[k] for k in ("roman", "name", "source", "status", "sources") if k in o}
    return {"roman": ["i" if bp.get("mode") == "minor" else "I"], "name": "Tonic", "source": "default",
            "status": "default", "sources": []}


def _voice_range(voice_range, voice_name, dna):
    if voice_range and voice_range[0] is not None and voice_range[1] is not None:
        return (float(voice_range[0]), float(voice_range[1])), \
            f"your trained voice{' “' + voice_name + '”' if voice_name else ''}"
    mel = (dna or {}).get("traits", {}).get("melody")
    if mel:
        return (float(mel["range_low_midi"]) - 2, float(mel["range_high_midi"]) + 2), \
            "the range you write in (Artist DNA), ±2 semitones"
    return DEFAULT_VOICE, "a default C3–C5; add a voice profile for your real range"


def _heard(brief, field):
    return next((h["words"] for h in brief["heard"] if h["field"] == field), field)


def _era_name(atlas, era):
    return next(e["name"] for e in atlas["eras"] if e["id"] == era)


def _title(prompt):
    words = (prompt or "").strip().split()
    return (" ".join(words[:6]).rstrip(",.;:") + ("…" if len(words) > 6 else "")) if words else "Untitled blueprint"


def _fmt_s(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


__all__ = ["BLUEPRINT_VERSION", "ROLES", "SECTION_TYPES", "build_blueprint", "revise", "regenerate"]
