"""AU-13 demo-to-song: a sung idea keeps its melody inside a full blueprint."""
import io

import numpy as np
import pytest
import soundfile as sf

from auralis.composer.arrange import arrange
from auralis.composer.chords import chord_tones, parse_key
from auralis.composer.demo import analyse_demo, build_from_demo, harmonize, key_from_notes, melody_to_beats
from auralis.voice.guide import GuideNote
from auralis.voice.singing_provider import get_singer

HOOK = [(0, 1, 62), (1, 1, 66), (2, 2, 69), (4, 1, 71), (5, 1, 69), (6, 2, 66), (8, 1, 64), (9, 1, 66),
        (10, 1, 67), (11, 1, 69), (12, 4, 66), (16, 1, 62), (17, 1, 66), (18, 2, 69), (20, 1, 74), (21, 1, 73),
        (22, 2, 71), (24, 1, 69), (25, 1, 67), (26, 1, 66), (27, 1, 64), (28, 4, 62)]          # D major
MINOR = [(0, 1, 57), (1, 1, 60), (2, 2, 64), (4, 1, 62), (5, 1, 60), (6, 2, 59), (8, 1, 57), (9, 1, 59),
         (10, 1, 60), (11, 1, 62), (12, 4, 64), (16, 1, 64), (17, 1, 65), (18, 2, 64), (20, 1, 62), (21, 1, 60),
         (22, 2, 59), (24, 1, 60), (25, 1, 59), (26, 1, 57), (27, 1, 56), (28, 4, 57)]        # A minor
EIGHTHS = [(i * 0.5, 0.5, [62, 64, 66, 67, 69, 67, 66, 64][i % 8]) for i in range(40)] + [(20, 4, 62)]


def _sing(hook, tempo, shift=0):
    """A phone-memo-like demo: the guide singer on its own, no click, a little hiss."""
    spb = 60 / tempo
    score = [GuideNote(start=0.5 + b * spb, duration=l * spb * 0.92, midi=m + shift, velocity=95, syllable="",
                       vowel="a", onset="", phrase_end=False) for b, l, m in hook]
    y = get_singer().sing(score, 0.5 + (max(b + l for b, l, _ in hook) + 2) * spb)
    return y + 0.003 * np.random.default_rng(0).standard_normal(len(y)).astype(np.float32)


@pytest.mark.parametrize("hook,tempo,shift,key", [
    (HOOK, 100, 0, "D major"), (HOOK, 88, 3, "F major"), (MINOR, 76, 0, "A minor"), (EIGHTHS, 92, 0, "D major"),
])
def test_gate_demo_tempo_key_and_melody_are_recovered(hook, tempo, shift, key):
    demo = analyse_demo(_sing(hook, tempo, shift), 44100)
    assert abs(demo["tempo"] - tempo) <= 1.0
    assert parse_key(demo["key"]) == parse_key(key)
    line = melody_to_beats(demo["notes"], demo["tempo"])
    assert [n[2] for n in line] == [m + shift for _, _, m in hook]                  # every pitch kept
    assert [n[0] for n in line] == [float(b) for b, _, _ in hook]                   # every onset on its 16th


def test_gate_blueprint_keeps_the_demo_as_the_chorus():
    demo = analyse_demo(_sing(HOOK, 100), 44100)
    bp = build_from_demo(demo, "90s R&B", voice_range=(50.0, 72.0), era="90s_rnb", role="chorus")
    assert bp["validation"]["ok"], bp["validation"]
    assert bp["key"] == "D major" and abs(bp["tempo"] - 100) <= 1 and bp["demo"]["bars"] == 8
    tonic, mode = parse_key(bp["key"])
    arranged = arrange(bp)["tracks"]["melody"]
    for s in bp["sections"]:
        start = (s["start_bar"] - 1) * 4
        inside = [n for n in arranged if start <= n[0] < start + s["bars"] * 4]
        if s["type"] == "chorus":
            assert [n[2] for n in inside] == [m for _, _, m in HOOK]               # every chorus sings the demo
            assert s["progression"]["source"] == "demo" and s["chords_per_bar"] == 1
            tones = sum((n[2] % 12) in {(chord_tones(c["roman"], tonic, mode)[0] + i) % 12
                                        for i in chord_tones(c["roman"], tonic, mode)[1]}
                        for n in inside for c in s["chords"]
                        if (c["bar"] - 1) * 4 <= n[0] - start < (c["bar"] - 1) * 4 + c["beats"])
            assert tones / len(inside) >= 0.7                                        # chords fit the melody
    assert any(s["type"] == "verse" for s in bp["sections"])                         # the rest of the song exists
    assert bp["why"]["demo"]


def test_harmonize_and_key_helpers():
    line = [(float(b), float(l), m, 90) for b, l, m in HOOK]
    chords, why = harmonize(line, 2, "major", 8)
    assert chords[0] == "I" and chords[-1] == "I" and len(chords) == 8 and why
    notes = [{"start": b * 0.6, "end": (b + l) * 0.6, "midi": m} for b, l, m in MINOR]
    assert key_from_notes(notes)[:2] == (9, "minor")


def test_no_melody_is_a_clear_error():
    with pytest.raises(ValueError, match="No clear melody"):
        analyse_demo(0.001 * np.random.default_rng(1).standard_normal(44100 * 5).astype(np.float32), 44100)


def test_api_demo(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from auralis.api import artist, main
    from auralis.artist.library import LibraryStore

    monkeypatch.setattr(artist, "LIBRARY", LibraryStore(tmp_path / "artist"))
    buf = io.BytesIO()
    sf.write(buf, _sing(HOOK, 100), 44100, format="WAV")
    client = TestClient(main.app)
    r = client.post("/composer/demo", data={"role": "chorus", "use_voice": "false", "use_dna": "false"},
                    files={"file": ("memo.wav", buf.getvalue(), "audio/wav")})
    assert r.status_code == 200, r.text
    bp = r.json()
    assert bp["demo"]["note_count"] == len(HOOK) and bp["key"] == "D major"
    assert client.post("/composer/demo", data={"role": "intro"},
                       files={"file": ("memo.wav", buf.getvalue(), "audio/wav")}).status_code == 422


# ── Session 017: played chords, pickups ────────────────────────────────────

from auralis.generation.synth import Instruments

D_PROG = [[50, 54, 57], [47, 50, 54], [43, 47, 50], [45, 49, 52]] * 2        # D Bm G A: I vi IV V, twice


def _piano(chords, tempo, n, start=0.5, level=0.25):
    spb = 60 / tempo
    inst = Instruments(0)
    out = np.zeros(n, np.float32)
    for i, notes in enumerate(chords):
        for p in notes:
            x = inst.ep(p, 4 * spb * 0.95, 80)
            a = int((start + i * 4 * spb) * 44100)
            m = min(len(x), n - a)
            if m > 0:
                out[a:a + m] += x[:m] * level
    return out


def _hiss(y):
    return y + 0.003 * np.random.default_rng(0).standard_normal(len(y)).astype(np.float32)


def test_singing_alone_is_never_heard_as_an_instrument():
    demo = analyse_demo(_sing(HOOK, 100), 44100)
    assert demo["has_instrument"] is False and demo["played_chords"] == [] and demo["pickup_beats"] == 0.0


def test_gate_chords_played_on_an_instrument_are_kept_as_played():
    piano = _hiss(_piano(D_PROG, 100, int(44100 * 21)))
    demo = analyse_demo(piano, 44100, tempo_hint=100)
    assert demo["has_instrument"] and demo["key"] == "D major"
    read = [c["roman"] for c in demo["played_chords"] if c["roman"]]
    assert read == ["I", "vi", "IV", "V"] * 2                                   # release tail not a bar
    bp = build_from_demo(demo, "90s R&B", voice_range=(50.0, 72.0), era="90s_rnb")
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    assert chorus["progression"]["roman"] == ["I", "vi", "IV", "V"] * 2 and bp["demo"]["played_chord_bars"] == 8
    start = (chorus["start_bar"] - 1) * 4
    melody = [n for n in arrange(bp)["tracks"]["melody"] if start <= n[0] < start + chorus["bars"] * 4]
    assert melody                                                               # the composer writes the tune


def test_singing_over_a_quieter_instrument_reads_its_chords():
    voice = _sing(HOOK, 100)
    demo = analyse_demo(_hiss(voice + _piano(D_PROG, 100, len(voice), level=0.08)), 44100)
    assert demo["has_instrument"] and demo["key"] == "D major" and abs(demo["tempo"] - 100) <= 1
    read = [c["roman"] for c in demo["played_chords"][:8]]
    assert sum(a == b for a, b in zip(read, ["I", "vi", "IV", "V"] * 2)) >= 7


SEVENTHS = [[50, 54, 57, 61], [47, 50, 54, 57], [43, 47, 50, 54], [45, 49, 52, 55]] * 2   # Dmaj7 Bm7 Gmaj7 A7


def test_gate_seventh_chords_are_read_as_sevenths_and_triads_stay_triads():
    demo = analyse_demo(_hiss(_piano(SEVENTHS, 100, int(44100 * 21))), 44100, tempo_hint=100)
    assert demo["key"] == "D major"                              # not the upper triads' key (F♯ minor)
    read = [c["roman"] for c in demo["played_chords"] if c["roman"]]
    assert read == ["Imaj7", "vi7", "IVmaj7", "V7"] * 2
    bp = build_from_demo(demo, "90s R&B", voice_range=(50.0, 72.0), era="90s_rnb")
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    assert chorus["progression"]["roman"] == ["Imaj7", "vi7", "IVmaj7", "V7"] * 2
    assert "7" not in "".join(c["roman"] or "" for c in
                              analyse_demo(_hiss(_piano(D_PROG, 100, int(44100 * 21))), 44100,
                                           tempo_hint=100)["played_chords"])   # overtones aren't sevenths


PICKUP = [(0, 0.5, 57), (0.5, 0.5, 59)] + [(b + 1, l, m) for b, l, m in HOOK]   # two eighths, then the hook


def test_gate_pickup_notes_from_the_phrasing():
    demo = analyse_demo(_sing(PICKUP, 100), 44100)
    assert demo["pickup_beats"] == 1.0
    line = melody_to_beats(demo["notes"], demo["tempo"], demo["pickup_beats"])
    assert [n[0] for n in line[:3]] == [-1.0, -0.5, 0.0] and [n[2] for n in line[:3]] == [57, 59, 62]
    bp = build_from_demo(demo, "90s R&B", voice_range=(50.0, 72.0), era="90s_rnb")
    chorus = next(s for s in bp["sections"] if s["type"] == "chorus")
    start = (chorus["start_bar"] - 1) * 4
    melody = arrange(bp)["tracks"]["melody"]
    lead_in = [n for n in melody if start - 1 <= n[0] < start]
    assert [(n[0] - start, n[2]) for n in lead_in] == [(-1.0, 57), (-0.5, 59)]   # sung just before the chorus
    assert not any(n[0] < start - 1 < n[0] + n[1] for n in melody)              # nothing rings into the pickup
    assert bp["validation"]["ok"]


def test_pickup_from_where_played_chords_change():
    voice = _sing(PICKUP, 100)
    piano = _piano(D_PROG, 100, len(voice), start=0.5 + 0.6, level=0.08)        # chords start on the bar line
    demo = analyse_demo(_hiss(voice + piano), 44100)
    assert demo["pickup_beats"] == 1.0


def test_pickup_can_be_set_by_hand():
    demo = analyse_demo(_sing(HOOK, 100), 44100, pickup_beats=2.0)
    line = melody_to_beats(demo["notes"], demo["tempo"], demo["pickup_beats"])
    assert line[0][0] == -2.0


def test_api_demo_pickup_override(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from auralis.api import artist, main
    from auralis.artist.library import LibraryStore

    monkeypatch.setattr(artist, "LIBRARY", LibraryStore(tmp_path / "artist"))
    buf = io.BytesIO()
    sf.write(buf, _sing(PICKUP, 100), 44100, format="WAV")
    client = TestClient(main.app)
    base = {"role": "chorus", "use_voice": "false", "use_dna": "false"}
    auto = client.post("/composer/demo", data=base, files={"file": ("m.wav", buf.getvalue(), "audio/wav")}).json()
    assert auto["demo"]["pickup_beats"] == 1.0
    forced = client.post("/composer/demo", data=base | {"pickup_beats": "0"},
                         files={"file": ("m.wav", buf.getvalue(), "audio/wav")}).json()
    assert forced["demo"]["pickup_beats"] == 0.0
    assert client.post("/composer/demo", data=base | {"pickup_beats": "9"},
                       files={"file": ("m.wav", buf.getvalue(), "audio/wav")}).status_code == 422
