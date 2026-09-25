"""AU-06 Atmosphere Engine: plan follows key/sections/energy; render follows key, tempo and energy."""
import librosa
import numpy as np
import pytest
from scipy.stats import spearmanr

from auralis.composer import build_blueprint, revise
from auralis.composer.chords import chord_tones, parse_key
from auralis.generation.atmosphere import ERA, plan_atmosphere, render_atmosphere, SR

VOICE = (50.0, 72.0)


def _bp(era="2000s_rnb", key="E♭ major", tempo=90):
    return build_blueprint("", voice_range=VOICE, era=era, key=key, tempo=tempo)


def _section_at(bp, beat):
    return next(s for s in bp["sections"] if (s["start_bar"] - 1) * 4 <= beat < (s["start_bar"] - 1 + s["bars"]) * 4)


def _render(bp, plan):
    spb = 60 / bp["tempo"]
    n = int(bp["total_bars"] * 4 * spb * SR) + 4 * SR
    return render_atmosphere(plan, bp["tempo"], n).mean(1), spb


def _section_rms(bp, mono, spb):
    return [float(np.sqrt((mono[int((s["start_bar"] - 1) * 4 * spb * SR):
                               int((s["start_bar"] - 1 + s["bars"]) * 4 * spb * SR)] ** 2).mean()))
            for s in bp["sections"]]


def test_blueprint_carries_atmosphere_levels_and_palette():
    modern, soul = _bp("modern_alt_rnb", "F minor"), _bp("70s_soul", "C major")
    lv = lambda bp, t: next(s for s in bp["sections"] if s["type"] == t)["arrangement"]["atmos"]
    assert lv(modern, "verse") == "medium" and lv(soul, "verse") == "light"       # era taste
    assert lv(modern, "chorus") == "full"
    assert modern["atmosphere"]["layers"] and modern["why"]["atmosphere"]
    assert "vinyl" in soul["atmosphere"]["layers"][0]
    assert modern["validation"]["ok"] and soul["validation"]["ok"]


def test_every_pitched_layer_follows_the_key_and_chords():
    bp = _bp()
    tonic, mode = parse_key(bp["key"])
    plan = plan_atmosphere(bp)
    assert {"bed", "drone", "pad", "shimmer", "swell"} <= set(plan["counts"])
    for layer in plan["layers"]:
        if layer["kind"] in ("pad", "shimmer", "choir", "sparkle"):
            s = _section_at(bp, layer["start"])
            chord = next(c for c in s["chords"]
                         if (s["start_bar"] - 1) * 4 + (c["bar"] - 1) * 4 + (c["beat"] - 1) == layer["start"])
            root, tones, _ = chord_tones(chord["roman"], tonic, mode)
            assert {p % 12 for p in layer["pitches"]} <= {(root + t) % 12 for t in tones}
        if layer["kind"] == "drone":
            assert layer["pitches"][0] % 12 == tonic and layer["pitches"][1] % 12 == (tonic + 7) % 12


def test_swells_land_on_the_downbeat_of_rising_sections():
    bp = _bp()
    plan = plan_atmosphere(bp)
    swells = [l for l in plan["layers"] if l["kind"] == "swell"]
    assert swells
    starts = {(s["start_bar"] - 1) * 4: s for s in bp["sections"]}
    for sw in swells:
        target = starts[sw["start"] + sw["beats"]]          # ends exactly on a section start
        before = _section_at(bp, sw["start"])
        assert target["type"] == "chorus" or target["energy"] >= before["energy"] + 0.1


def test_atmos_level_is_editable_per_section():
    bp = _bp()
    verse = next(s for s in bp["sections"] if s["type"] == "verse")
    changes = {"sections": [{"id": s["id"], "arrangement": dict(s["arrangement"], atmos="off")}
                            if s["id"] == verse["id"] else {"id": s["id"]} for s in bp["sections"]]}
    edited = revise(bp, changes)
    assert edited["validation"]["ok"]
    start, end = (verse["start_bar"] - 1) * 4, (verse["start_bar"] - 1 + verse["bars"]) * 4
    inside = [l for l in plan_atmosphere(edited)["layers"]
              if l["kind"] not in ("bed", "swell") and start <= l["start"] < end]
    assert inside == []
    # blueprints saved before AU-06 (no atmos key) still get an era default
    old = dict(bp, sections=[dict(s, arrangement={k: v for k, v in s["arrangement"].items() if k != "atmos"})
                             for s in bp["sections"]])
    assert plan_atmosphere(old)["levels"] == [s["arrangement"]["atmos"] for s in bp["sections"]]


def test_era_palettes_differ():
    neo = plan_atmosphere(_bp("neo_soul", "F minor"))
    modern = plan_atmosphere(_bp("modern_alt_rnb", "F minor"))
    assert "choir" not in neo["counts"] and "choir" in modern["counts"]
    assert neo["layers"][0]["style"] == ERA["neo_soul"]["bed"] == "vinyl"
    assert modern["layers"][0]["style"] == "air"


@pytest.mark.parametrize("era,key", [("2000s_rnb", "E♭ major"), ("modern_alt_rnb", "F minor")])
def test_gate_render_follows_key_tempo_and_energy(era, key):
    """Ground truth on the audio: in key, on the grid, louder where the song is bigger."""
    bp = _bp(era, key)
    plan = plan_atmosphere(bp)
    mono, spb = _render(bp, plan)
    tonic, mode = parse_key(key)
    scale = [0, 2, 4, 5, 7, 9, 11] if mode == "major" else [0, 2, 3, 5, 7, 8, 10]
    chroma = librosa.feature.chroma_cqt(y=mono[::2].astype(np.float32), sr=SR // 2).mean(1)
    assert chroma[[(tonic + i) % 12 for i in scale]].sum() / chroma.sum() > 0.85          # key
    rms = _section_rms(bp, mono, spb)
    inner = [(s["energy"], r) for s, r in zip(bp["sections"], rms) if s["type"] not in ("intro", "outro")]
    assert spearmanr(*zip(*inner)).correlation >= 0.8                                    # energy
    by = {s["type"]: r for s, r in zip(bp["sections"], rms)}
    assert by["chorus"] > by["verse"] and by["chorus"] > by["pre-chorus"]
    # tempo: the sparkle ear candy sits on the eighth-note grid
    sparkle = [l for l in plan["layers"] if l["kind"] == "sparkle"][:4]
    if era != "neo_soul":
        solo, _ = _render(bp, dict(plan, layers=sparkle))
        a = int(sparkle[0]["start"] * spb * SR)
        onsets = librosa.onset.onset_detect(y=solo[a:a + int(8 * spb * SR)].astype(np.float32), sr=SR,
                                            units="time", backtrack=True)
        eighth = spb / 2
        dev = [min((o / eighth) % 1, 1 - (o / eighth) % 1) * eighth for o in onsets]
        assert len(onsets) >= 8 and np.median(dev) < 0.025


def test_mixer_gain_offsets_are_opt_in():
    from auralis.engine.analysis import StemAnalysis
    from auralis.engine.mixer import mix

    import dataclasses
    fields = {f.name for f in dataclasses.fields(StemAnalysis)}
    base = {k: 0.0 for k in fields}
    base.update(path="a.wav", role="other", integrated_lufs=-20.0)
    a = StemAnalysis(**{k: base.get(k, None) for k in fields})
    plain = mix([a])[0].gain_db
    assert mix([a], gain_offsets={"a.wav": -6.0})[0].gain_db == pytest.approx(plain - 6.0)
    assert mix([a], gain_offsets={"other.wav": -6.0})[0].gain_db == plain


def test_render_instrumental_includes_atmosphere_stem_and_midi(tmp_path):
    from auralis.composer.midi import read_midi
    from auralis.generation import render_instrumental

    bp = _bp(tempo=120)
    by_type = {}
    for s in bp["sections"]:
        by_type.setdefault(s["type"], s["id"])
    bp = revise(bp, {"sections": [{"id": by_type[t], "bars": b} for t, b in
                                  [("intro", 2), ("verse", 2), ("pre-chorus", 2), ("chorus", 4), ("outro", 2)]]})
    out = render_instrumental(bp, str(tmp_path / "r"), master=False)
    assert "atmosphere" in out["stems"] and out["atmosphere"]["counts"]["swell"] >= 1
    assert all(l["why"] for l in out["atmosphere"]["layers"])
    names = {t["name"] for t in read_midi(out["midi_path"])["tracks"]}
    assert "Atmosphere" in names
