"""Artist DNA V1: recurring traits across the user's own catalog.

Aggregates the per-song analyses (``analyze.py``) of songs the user has left
switched on in My Music. Nothing is generated here. The goal is an
*inspectable* description of how this artist writes, where every trait says
what it was measured from and how much to trust it.

Weighting, and why (all visible in the output under ``method``):

* A song the user switched off counts for nothing.
* Stem sets count more than full mixes: their melody, rhythm and form come
  from separated stems, which is more reliable (see AU-02 findings).
* Covers and type-beat packages count less. They are the most likely to be
  someone else's writing.
* Versions of one song (vocal, instrumental, remixes of it) share one song's
  worth of weight, so a track with five remixes does not outvote five
  different songs.

Keys are grouped by **key signature** (relative major/minor together). The
AU-02 cross-check showed the detector finds the right key family more reliably
than the exact tonic, so the family is the trait and the tonic is a detail.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

DNA_VERSION = 1

KIND_WEIGHT = {"stem-set": 1.0, "mix": 0.7}
VARIANT_WEIGHT = {"cover": 0.3, "type-beat": 0.5}

# Major-key tonic pitch class -> accidentals in its signature.
_SIGNATURE = {0: "0", 7: "1♯", 2: "2♯", 9: "3♯", 4: "4♯", 11: "5♯", 6: "6♯/6♭",
              1: "5♭", 8: "4♭", 3: "3♭", 10: "2♭", 5: "1♭"}
_PC = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
_NOISE = r"\b(instrumental|inst|remix|suite|cover|demo|version|mix|rnb|r&b|edm|techno|trap|dark|" \
         r"house|deep|tech|drill|groovy|grovvy|rave|type|style|performance|track|final|master|feat\.?.*)\b"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def family_key(title: str) -> str:
    """A song's base name, so its versions can share weight."""
    t = title.lower()
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)
    t = re.sub(_NOISE, " ", t)
    t = re.sub(r"[^a-z ]+", " ", t)
    return " ".join(t.split())


def _families(titles: dict[str, str]) -> dict[str, str]:
    """song id -> family id. A title whose words start with a shorter title's
    (2+ words) joins that family, so "velvet hour trap" joins "velvet hour"."""
    base = {sid: family_key(t) for sid, t in titles.items()}
    names = sorted({b for b in base.values() if b}, key=lambda b: len(b.split()))
    out = {}
    for sid, b in base.items():
        words = b.split()
        fam = b or sid
        for cand in names:
            cw = cand.split()
            if len(cw) >= 2 and words[:len(cw)] == cw:
                fam = cand
                break
        out[sid] = fam
    return out


def _wquantile(values, weights, q):
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    if v.size == 0 or w.sum() <= 0:
        return None
    order = np.argsort(v)
    v, w = v[order], w[order]
    cw = np.cumsum(w) / w.sum()
    return float(np.interp(q, cw - w / (2 * w.sum()), v))


def _wmean(values, weights):
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    return float((v * w).sum() / w.sum()) if v.size and w.sum() > 0 else None


def _signature(tonic: int, mode: str) -> tuple[int, str]:
    major = tonic if mode == "major" else (tonic + 3) % 12
    minor = (major + 9) % 12
    return major, f"{_SIGNATURE[major]} · {_PC[major]} major / {_PC[minor]} minor"


def _note(midi: float | None) -> str | None:
    if midi is None:
        return None
    m = int(round(midi))
    names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
    return f"{names[m % 12]}{m // 12 - 1}"


def _evidence(rows, weights, n=5):
    """The songs that contribute most, for 'why do you say that?'."""
    ranked = sorted(zip(rows, weights), key=lambda rw: -rw[1])
    return [{"song_id": r["id"], "title": r["title"]} for r, w in ranked[:n] if w > 0]


def _confidence(n: int, strong: int = 12, some: int = 5) -> str:
    return "strong" if n >= strong else "moderate" if n >= some else "weak"


def build_dna(songs: list, analyses: dict[str, dict], voice=None) -> dict:
    """Aggregate analyses into Artist DNA. ``songs`` are library Song objects."""
    rows = []
    for s in songs:
        a = analyses.get(s.id)
        if not a or s.analysis_status != "done":
            continue
        rows.append({"id": s.id, "title": s.title, "kind": s.kind, "variants": s.variants,
                     "included": s.included, "a": a})
    used = [r for r in rows if r["included"]]
    fam = _families({r["id"]: r["title"] for r in used})
    fam_size = Counter(fam.values())
    for r in used:
        w = KIND_WEIGHT.get(r["kind"], 0.7)
        for v in r["variants"]:
            w *= VARIANT_WEIGHT.get(v, 1.0)
        r["w"] = w / fam_size[fam[r["id"]]]
        r["family"] = fam[r["id"]]

    out: dict = {
        "dna_version": DNA_VERSION,
        "built_at": _now(),
        "method": {
            "songs_analysed": len(rows),
            "songs_used": len(used),
            "songs_switched_off": len(rows) - len(used),
            "song_families": len(fam_size),
            "stem_sets_used": sum(r["kind"] == "stem-set" for r in used),
            "weights": {"kind": KIND_WEIGHT, "variant": VARIANT_WEIGHT,
                        "versions_of_one_song": "share one song's weight"},
        },
        "traits": {},
    }
    if not used:
        out["empty"] = True
        return out
    T = out["traits"]
    W = [r["w"] for r in used]

    # ── Tempo ──────────────────────────────────────────────────────────────
    bpm = [r["a"]["tempo"]["bpm"] for r in used]
    lo, mid, hi = (_wquantile(bpm, W, q) for q in (0.25, 0.5, 0.75))
    bands = Counter()
    for b, w in zip(bpm, W):
        bands[f"{int(b // 10 * 10)}s"] += w
    tot = sum(bands.values())
    ambiguous = sum(w for r, w in zip(used, W) if r["a"]["tempo"]["bpm"] >= 110) / sum(W)
    T["tempo"] = {
        "summary": f"{round(lo)}–{round(hi)} BPM, centred on {round(mid)}",
        "low": round(lo, 1), "median": round(mid, 1), "high": round(hi, 1),
        "bands": {k: round(v / tot, 3) for k, v in sorted(bands.items(), key=lambda kv: int(kv[0][:-1]))},
        "note": (f"{round(ambiguous * 100)}% of the weight sits at 110+ BPM, where a slow groove "
                 "can read at double time; half-time alternates are kept per song."),
        "confidence": _confidence(len(used)),
        "evidence": _evidence(used, W),
    }

    # ── Key family ─────────────────────────────────────────────────────────
    sig_w, sig_name, mode_w, tonic_w = Counter(), {}, Counter(), Counter()
    for r, w in zip(used, W):
        k = r["a"]["key"]
        major, name = _signature(k["tonic"], k["mode"])
        sig_w[major] += w
        sig_name[major] = name
        mode_w[k["mode"]] += w
        tonic_w[k["name"]] += w
    tot = sum(sig_w.values())
    top = sig_w.most_common(4)
    T["key"] = {
        "summary": (f"{round(mode_w['minor'] / tot * 100)}% minor; "
                    + (f"most often {sig_name[top[0][0]]}" if top[0][1] / tot >= 0.25
                       else f"spread across keys (top family only {round(top[0][1] / tot * 100)}%)")),
        "minor_share": round(mode_w["minor"] / tot, 3),
        "families": [{"signature": sig_name[m], "major_tonic": m, "share": round(w / tot, 3)} for m, w in top],
        "exact_keys": [{"key": k, "share": round(w / tot, 3)} for k, w in tonic_w.most_common(5)],
        "note": "Families (relative major/minor together) are the trait; exact tonics are less reliable.",
        "confidence": _confidence(len(used)),
    }

    # ── Harmony ────────────────────────────────────────────────────────────
    rate = [r["a"]["harmony"]["changes_per_bar"] for r in used]
    diat = [r["a"]["harmony"]["diatonic_share"] for r in used]
    by_mode: dict[str, Counter] = {"major": Counter(), "minor": Counter()}
    vocab: dict[str, Counter] = {"major": Counter(), "minor": Counter()}
    for r, w in zip(used, W):
        mode = r["a"]["key"]["mode"]
        seen = set()
        for p in r["a"]["harmony"]["top_progressions"]:
            key = canonical_loop(p["progression"])
            if key not in seen:          # count songs that use it, not repeats
                by_mode[mode][key] += w
                seen.add(key)
        for chord, share in r["a"]["harmony"]["vocabulary"].items():
            vocab[mode][chord] += w * share
    T["harmony"] = {
        "summary": (f"about {_wquantile(rate, W, 0.5):.1f} chord changes per bar, "
                    f"{round(_wquantile(diat, W, 0.5) * 100)}% inside the key"),
        "changes_per_bar": round(_wquantile(rate, W, 0.5), 2),
        "diatonic_share": round(_wquantile(diat, W, 0.5), 3),
        "loops": {m: [{"progression": k, "weight": round(v, 2)} for k, v in c.most_common(5)]
                  for m, c in by_mode.items() if c},
        "vocabulary": {m: [{"chord": k, "share": round(v / sum(c.values()), 3)} for k, v in c.most_common(8)]
                       for m, c in vocab.items() if c},
        "note": "Roman numerals are relative to each song's detected key; major- and minor-key songs are kept apart.",
        "confidence": _confidence(len(used)),
    }

    # ── Form and section lift ──────────────────────────────────────────────
    form_rows = [(r, w * (1.0 if r["kind"] == "stem-set" else 0.5)) for r, w in zip(used, W)]
    forms, first_chorus, intro_bars, lift = Counter(), [], [], []
    fc_w, ib_w, lift_w, role_bars = [], [], [], defaultdict(list)
    for r, w in form_rows:
        st = r["a"]["structure"]
        secs = st.get("sections", [])
        if not secs:
            continue
        roles_form = st.get("roles_form", "")
        if "C" in roles_form.split() and len(roles_form.split()) >= 4:
            forms[roles_form] += w
        choruses = [s for s in secs if s["role_guess"] == "chorus"]
        verses = [s for s in secs if s["role_guess"] == "verse"]
        if choruses:
            first_chorus.append(choruses[0]["start_seconds"]); fc_w.append(w)
        if secs[0]["role_guess"] == "intro":
            intro_bars.append(secs[0]["bars"]); ib_w.append(w)
        if choruses and verses:
            lift.append(np.mean([s["energy"] for s in choruses]) - np.mean([s["energy"] for s in verses]))
            lift_w.append(w)
        for s in secs:
            role_bars[s["role_guess"]].append(s["bars"])
    T["form"] = {
        "summary": (f"first chorus around {_fmt_s(_wquantile(first_chorus, fc_w, 0.5))}"
                    + (f", intros about {round(_wquantile(intro_bars, ib_w, 0.5))} bars" if intro_bars else "")),
        "common_forms": [{"form": f, "weight": round(w, 2)} for f, w in forms.most_common(4) if f],
        "first_chorus_seconds": _r(_wquantile(first_chorus, fc_w, 0.5)),
        "intro_bars": _r(_wquantile(intro_bars, ib_w, 0.5)),
        "section_bars": {role: round(float(np.median(v)), 1) for role, v in role_bars.items() if len(v) >= 3},
        "chorus_lift": _r(_wmean(lift, lift_w), 3),
        "note": "Section roles are guesses; stem sets count double here because their form comes from stem activity.",
        "confidence": _confidence(len(fc_w)),
    }

    # ── Groove ─────────────────────────────────────────────────────────────
    gw = [w * (1.0 if r["a"]["rhythm"]["source"] == "drums stem" else 0.6) for r, w in zip(used, W)]
    sync = [r["a"]["rhythm"]["syncopation"] for r in used]
    dens = [r["a"]["rhythm"]["onsets_per_beat"] for r in used]
    swing_pairs = [(r["a"]["rhythm"]["swing_position"], w) for r, w in zip(used, gw)
                   if r["a"]["rhythm"].get("swing_position") is not None]
    swing = _wquantile([p for p, _ in swing_pairs], [w for _, w in swing_pairs], 0.5) if swing_pairs else None
    s_med = _wquantile(sync, gw, 0.5)
    T["groove"] = {
        "summary": (f"{'syncopated' if s_med > 0.45 else 'mostly on the beat'} "
                    f"({round(s_med * 100)}% of hits off the beat), "
                    f"{'swung' if swing and swing > 0.58 else 'straight'} feel"),
        "syncopation": round(s_med, 3),
        "onsets_per_beat": round(_wquantile(dens, gw, 0.5), 2),
        "swing_position": _r(swing, 3),
        "note": "Drum stems count more than drums estimated from a full mix.",
        "confidence": _confidence(len(used)),
    }

    # ── Melody (lead vocal stems only) ─────────────────────────────────────
    mel = [(r, w) for r, w in zip(used, W) if r["a"].get("melody")]
    if mel:
        mw = [w for _, w in mel]
        low = _wquantile([r["a"]["melody"]["range_low_midi"] for r, _ in mel], mw, 0.5)
        high = _wquantile([r["a"]["melody"]["range_high_midi"] for r, _ in mel], mw, 0.5)
        centre = (low + high) / 2
        phrase = [r["a"]["melody"]["phrase_beats_median"] for r, _ in mel if r["a"]["melody"]["phrase_beats_median"]]
        ip = lambda k: _wquantile([r["a"]["melody"]["interval_profile"][k] or 0 for r, _ in mel], mw, 0.5)
        T["melody"] = {
            "summary": (f"sits around {_note(low)}–{_note(high)}, "
                        f"{round(ip('step') * 100)}% stepwise motion, phrases about "
                        f"{round(float(np.median(phrase)), 1) if phrase else '?'} beats"),
            "range_low": _note(low), "range_high": _note(high),
            "range_low_midi": round(low, 1), "range_high_midi": round(high, 1),
            "centre": _note(centre),
            "phrase_beats": round(float(np.median(phrase)), 1) if phrase else None,
            "motion": {k: round(ip(k), 3) for k in ("repeat", "step", "skip", "leap")},
            "confidence": _confidence(len(mel), strong=10, some=4),
            "evidence": _evidence([r for r, _ in mel], mw),
        }

    # ── Production ─────────────────────────────────────────────────────────
    g = lambda f: [f(r["a"]) for r in used]
    vtm = [(r["a"]["production"]["vocal_to_music_db"], w) for r, w in zip(used, W)
           if r["a"]["production"].get("vocal_to_music_db") is not None]
    T["production"] = {
        "summary": (f"{_wquantile(g(lambda a: a['global']['integrated_lufs']), W, 0.5):.1f} LUFS, "
                    f"width {_wquantile(g(lambda a: a['global']['stereo_width']), W, 0.5):.2f}, "
                    f"{round(_wquantile(g(lambda a: a['production']['low_ratio']), W, 0.5) * 100)}% of energy below 250 Hz"),
        "lufs": round(_wquantile(g(lambda a: a["global"]["integrated_lufs"]), W, 0.5), 1),
        "loudness_range_lu": _r(_wquantile([x for x in g(lambda a: a["global"]["loudness_range_lu"]) if x is not None],
                                           [w for w, x in zip(W, g(lambda a: a["global"]["loudness_range_lu"])) if x is not None], 0.5), 1),
        "stereo_width": round(_wquantile(g(lambda a: a["global"]["stereo_width"]), W, 0.5), 3),
        "low_ratio": round(_wquantile(g(lambda a: a["production"]["low_ratio"]), W, 0.5), 3),
        "vocal_to_music_db": _r(_wquantile([v for v, _ in vtm], [w for _, w in vtm], 0.5), 1) if vtm else None,
        "confidence": _confidence(len(used)),
    }

    # ── Voice fit ──────────────────────────────────────────────────────────
    if voice is not None and voice.pitch_low_midi is not None and "melody" in T:
        m = T["melody"]
        T["voice"] = {
            "profile_id": voice.id, "profile_name": voice.name,
            "trained_range": f"{_note(voice.pitch_low_midi)}–{_note(voice.pitch_high_midi)}",
            "writing_range": f"{m['range_low']}–{m['range_high']}",
            "headroom_semitones": round(voice.pitch_high_midi - m["range_high_midi"], 1),
            "footroom_semitones": round(m["range_low_midi"] - voice.pitch_low_midi, 1),
            "summary": (f"you write {m['range_low']}–{m['range_high']}; your trained voice covers "
                        f"{_note(voice.pitch_low_midi)}–{_note(voice.pitch_high_midi)}"),
            "note": "Headroom above your usual melody top is room for a chorus lift.",
        }
    return out


def canonical_loop(chords: list[str]) -> str:
    """One name per repeating loop: i–v–i–v and v–i–v–i are the same loop.

    Picks the rotation that starts on the tonic (I or i) when there is one,
    else the alphabetically first rotation, so the choice is stable.
    """
    n = len(chords)
    rotations = [chords[i:] + chords[:i] for i in range(n)]
    tonic = [r for r in rotations if r[0] in ("I", "i")]
    best = min(tonic or rotations, key=lambda r: " ".join(r))
    return " – ".join(best)


def _r(x, n=1):
    return None if x is None else round(float(x), n)


def _fmt_s(seconds):
    if seconds is None:
        return "?"
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
