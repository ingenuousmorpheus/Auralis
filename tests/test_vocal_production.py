"""AU-09 vocal production: doubles, harmonies, ad-libs as separate stems."""
import shutil

import librosa
import numpy as np
import pytest
import soundfile as sf

from auralis.composer.arrange import arrange
from auralis.composer.chords import chord_tones, parse_key
from auralis.composer.vocal_parts import SCALES, plan_parts
from auralis.voice.guide import build_score
from auralis.voice.pitch import _track_pitch
from auralis.voice.singing_provider import get_singer
from auralis.voice.vocal_production import convert_parts, pack

from test_full_song import _short


def _score(bp, seed=0):
    return build_score(bp, arrange(bp, seed=seed)["tracks"]["melody"])


def _section(bp, t):
    beat = t * bp["tempo"] / 60
    return next(s for s in bp["sections"] if (s["start_bar"] - 1) * 4 <= beat < (s["start_bar"] - 1 + s["bars"]) * 4)


def test_parts_follow_backing_levels_and_production():
    bp = _short()
    score = _score(bp)
    full = plan_parts(bp, score, "full")
    assert all(full["counts"][p] for p in ("double_l", "double_r", "harmony_high", "harmony_low", "adlibs"))
    for n in full["parts"]["harmony_high"] + full["parts"]["harmony_low"]:
        assert _section(bp, n.start)["arrangement"]["backing_vocals"] in ("medium", "full")
    for n in full["parts"]["double_l"]:
        assert _section(bp, n.start)["arrangement"]["backing_vocals"] != "off"
    assert plan_parts(bp, score, "lead")["counts"] == {p: 0 for p in full["counts"]}
    doubles = plan_parts(bp, score, "doubles")["counts"]
    assert doubles["double_l"] and not doubles["harmony_high"] and not doubles["adlibs"]
    assert full["why"]


def test_harmonies_are_chord_tones_in_key_and_range():
    bp = _short()
    tonic, mode = parse_key(bp["key"])
    scale = {(tonic + i) % 12 for i in SCALES[mode]}
    lead = {round(n.start, 4): n for n in _score(bp)}
    plan = plan_parts(bp, list(lead.values()))
    lo, hi = bp["vocal"]["range_low_midi"], bp["vocal"]["range_high_midi"]
    for part, sign in (("harmony_high", 1), ("harmony_low", -1)):
        for n in plan["parts"][part]:
            ld = lead[round(n.start, 4)]
            gap = (n.midi - ld.midi) * sign
            assert 3 <= gap <= 9 and n.midi % 12 in scale and lo <= n.midi <= hi - 1
    # doubles are the lead a few ms apart (separate performances)
    for n in plan["parts"]["double_l"]:
        assert any(abs(n.start - s - 0.012) < 1e-6 and n.midi == lead[s].midi for s in lead)


def test_adlibs_only_fill_rests_at_the_end():
    bp = _short()
    score = _score(bp)
    plan = plan_parts(bp, score)
    lead_spans = [(n.start, n.start + n.duration) for n in score]
    for n in plan["parts"]["adlibs"]:
        assert _section(bp, n.start)["type"] in ("chorus", "outro")
        assert not any(a < n.start < b for a, b in lead_spans)


def test_pack_and_unpack_restore_positions():
    rng = np.random.default_rng(0)
    guides = {"lead": (0.2 * rng.standard_normal(44100 * 30)).astype(np.float32),
              "harmony_high": (0.2 * rng.standard_normal(44100 * 30)).astype(np.float32)}
    spans = {"lead": [(1.0, 6.0), (10.0, 14.0)], "harmony_high": [(2.0, 5.0)]}
    calls = []

    def identity(src, dst, q):
        calls.append(sf.info(src).duration)
        shutil.copyfile(src, dst)

    import tempfile
    out, n = convert_parts(guides, spans, identity, tempfile.mkdtemp(), "fast", max_seconds=60)
    assert n == 1 and len(calls) == 1
    for part, sp in spans.items():
        for a, b in sp:
            s0, s1 = int(a * 44100), int(b * 44100)
            assert np.allclose(out[part][s0:s1], guides[part][s0:s1], atol=1 / 32767 * 2)
    assert np.all(out["lead"][int(7 * 44100):int(9 * 44100)] == 0)             # unsung parts stay silent
    out2, n2 = convert_parts(guides, spans, identity, tempfile.mkdtemp(), "fast", max_seconds=8)
    assert n2 >= 2                                                              # split when calls get long
    assert len(pack([("a", np.zeros(44100 * 5, np.float32), 0)] * 3, max_seconds=12)) == 2   # 5+1.5+5 fits, a third does not


@pytest.mark.parametrize("key", ["A♭ major", "E minor"])
def test_gate_rendered_parts_are_on_their_written_pitch(key):
    """Each part's guide sings its own line: pYIN finds the written pitch (octave-strict)."""
    bp = _short(key=key)
    plan = plan_parts(bp, _score(bp))
    for part in ("harmony_high", "harmony_low", "double_l", "adlibs"):
        notes = plan["parts"][part]
        y = get_singer().sing(notes, bp["duration_seconds"] + 2, seed=7)
        z = librosa.resample(y, orig_sr=44100, target_sr=22050)
        t, f0, _ = _track_pitch(z, 22050)
        m = librosa.hz_to_midi(f0)
        ok = tot = 0
        for n in notes:
            sel = (t >= n.start + 0.06) & (t <= n.start + n.duration - 0.03)
            v = m[sel][np.isfinite(m[sel])]
            if len(v) < 3:
                continue
            tot += 1
            ok += abs(np.median(v) - n.midi) <= 0.5
        assert tot >= 3 and ok / tot >= 0.9, (part, ok, tot)


def test_gate_song_produces_lead_doubles_harmonies_as_separate_stems(tmp_path):
    from auralis.generation import render_instrumental
    from auralis.voice import VoiceProfileStore
    from auralis.voice.full_song import sing_song

    bp = _short()
    render = render_instrumental(bp, str(tmp_path / "r"))
    ref = tmp_path / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(44100 * 8) / 44100)).astype(np.float32), 44100)
    profile = VoiceProfileStore(tmp_path / "v").create("Stand In", str(ref), True)
    calls = []

    def identity(src, dst, q):
        calls.append(src)
        shutil.copyfile(src, dst)

    out = sing_song(bp, render, profile, str(tmp_path / "song"), identity, quality="fast")
    assert out["conversion_calls"] == len(calls) == 1                       # every part in one model load
    stems = out["backing_stems"]
    assert set(stems) == {"double_l", "double_r", "harmony_high", "harmony_low", "adlibs"}
    lead, _ = sf.read(out["finished_path"])
    paths = [out["finished_path"]] + list(stems.values()) + [out["backing_path"]]
    assert len(set(paths)) == len(paths)
    left, right = sf.read(stems["double_l"])[0], sf.read(stems["double_r"])[0]
    assert np.abs(left[:, 0]).sum() > np.abs(left[:, 1]).sum()                # panned left
    assert np.abs(right[:, 1]).sum() > np.abs(right[:, 0]).sum()              # panned right
    assert sf.info(out["song_master_path"]).channels == 2
    lead_only = sing_song(bp, render, profile, str(tmp_path / "song2"), identity, quality="fast",
                          production="lead", master=False)
    assert lead_only["backing_stems"] == {} and lead_only["backing_path"] is None


# ── Session 017: adjustable backing-vocal levels ───────────────────────────

def test_backing_levels_move_each_part_by_its_db(tmp_path):
    from auralis.voice.vocal_production import backing_bus

    tone = (0.2 * np.sin(2 * np.pi * 330 * np.arange(44100 * 2) / 44100)).astype(np.float32)
    base = backing_bus({"harmony_high": tone}, str(tmp_path / "a"))
    louder = backing_bus({"harmony_high": tone}, str(tmp_path / "b"), levels={"harmony_high": 6.0})
    ra = np.sqrt(np.mean(sf.read(base["stems"]["harmony_high"])[0] ** 2))
    rb = np.sqrt(np.mean(sf.read(louder["stems"]["harmony_high"])[0] ** 2))
    assert 20 * np.log10(rb / ra) == pytest.approx(6.0, abs=0.2)


def test_sing_song_records_backing_mix_settings(tmp_path):
    from auralis.generation import render_instrumental
    from auralis.voice import VoiceProfileStore
    from auralis.voice.full_song import sing_song

    bp = _short()
    render = render_instrumental(bp, str(tmp_path / "r"), master=False)
    ref = tmp_path / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(44100 * 8) / 44100)).astype(np.float32), 44100)
    profile = VoiceProfileStore(tmp_path / "v").create("Stand In", str(ref), True)
    out = sing_song(bp, render, profile, str(tmp_path / "song"), lambda s, d, q: shutil.copyfile(s, d),
                    quality="fast", master=False, backing_levels={"adlibs": -6.0}, backing_db=1.0)
    assert out["backing_levels"] == {"adlibs": -6.0} and out["backing_db"] == 1.0
