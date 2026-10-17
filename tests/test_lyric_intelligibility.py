"""Lyric intelligibility (Session 024): the gate for sung words.

The success criterion: a short, clearly defined phrase must come out of the
guide singer as recognisable words, in order, while keeping the target melody.
Words are judged by a speech recogniser (the cached local faster-whisper
``base`` model; skipped when it is not on the machine), melody by pyin.

Two problems were measured and are pinned here as strict expected failures, so
the fix flips them to passing (and pytest then asks for the marker to go):

1. The built-in vocalise guide sings vowels only: 0/7 words recognised, while
   every note is within a few cents (``test_guide_singer_sings_the_words``).
2. Lyric lines are not mapped one-to-one onto melody phrases: when a section
   has more phrases than lines, ``build_score`` loops the lines (sung out of
   order, repeated, truncated), and a chorus's repeated hook carries the wrong
   number of notes for its line (``test_each_lyric_line_is_sung_once_in_order``).
"""
from __future__ import annotations

import difflib
import os
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

NL = chr(10)
PHRASE = "take my hand and hold me close"
WORDS = PHRASE.split()
MIDI = [62, 64, 66, 67, 66, 64, 62]            # D major, one note per word
TEMPO = 90.0
BEATS = [1, 1, 1, 1, 1, 1, 2]
LEAD_BEATS = 0.75


def _phrase_score():
    from auralis.voice.guide import build_score

    blueprint = {"tempo": TEMPO, "sections": [{"start_bar": 1, "bars": 4, "type": "verse", "lyrics": [PHRASE]}]}
    melody = [(LEAD_BEATS + sum(BEATS[:i]), BEATS[i] * 0.92, MIDI[i], 90) for i in range(len(MIDI))]
    return build_score(blueprint, melody)


def _recogniser():
    fw = pytest.importorskip("faster_whisper")
    try:
        return fw.WhisperModel("base", device="cpu", compute_type="int8", local_files_only=True)
    except Exception as exc:                                      # model not cached here
        pytest.skip(f"local faster-whisper 'base' model not available: {exc}")


def _words_in_order(model, path) -> tuple[int, str]:
    segments, _ = model.transcribe(path, language="en", beam_size=5, temperature=0.0,
                                   condition_on_previous_text=False, vad_filter=False)
    text = " ".join(s.text.strip() for s in segments)
    heard = "".join(c if c.isalpha() or c in " '" else " " for c in text.lower()).split()
    matcher = difflib.SequenceMatcher(a=WORDS, b=heard)
    return sum(b.size for b in matcher.get_matching_blocks()), text


# ── the gate ─────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="The default guide is still vocalise (vowels, not words; 0/7 measured, "
                                       "Session 024). The experimental word guide passes this gate "
                                       "(tests/test_word_guide.py); it becomes the default only on owner approval.")
def test_guide_singer_sings_the_words(tmp_path):
    """The guide singer the pipeline uses must sing a short phrase intelligibly."""
    from auralis.models import REGISTRY

    model = _recogniser()
    singer = REGISTRY.guide_singer()
    score = _phrase_score()
    audio = singer.sing(score, score[-1].start + score[-1].duration + 1.0, seed=0)
    path = str(tmp_path / "guide.wav")
    sf.write(path, audio, 44100)
    hits, text = _words_in_order(model, path)
    assert hits >= 6, f"guide singer: {hits}/7 words in order; heard {text[:80]!r}"


def test_guide_keeps_the_target_melody(tmp_path):
    """Whatever the singer, every note must land on its pitch (vocalise: within a few cents)."""
    import librosa

    from auralis.voice.singing_provider import VocaliseSinger

    score = _phrase_score()
    audio = VocaliseSinger().sing(score, score[-1].start + score[-1].duration + 1.0, seed=0)
    f0, voiced, _ = librosa.pyin(audio, fmin=70, fmax=600, sr=44100, frame_length=4096, hop_length=512)
    times = librosa.times_like(f0, sr=44100, hop_length=512)
    for note in score:
        sel = (times >= note.start + 0.1 * note.duration) & (times <= note.start + 0.8 * note.duration) & voiced
        assert sel.sum() > 3, f"no pitch found for {note.syllable!r}"
        cents = (np.median(librosa.hz_to_midi(f0[sel])) - note.midi) * 100
        assert abs(cents) < 25, f"{note.syllable!r}: {cents:+.0f} cents off"


@pytest.mark.skipif(sys.platform != "win32", reason="uses the built-in Windows speech voice as a control")
def test_the_word_meter_hears_real_words(tmp_path):
    """Control: the same measurement recognises the phrase when it is really spoken,
    so a failing gate means the singer, not the meter."""
    model = _recogniser()
    path = str(tmp_path / "spoken.wav")
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{PHRASE}'); $s.Dispose()")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
    if done.returncode != 0 or not os.path.exists(path):
        pytest.skip("Windows speech synthesis is not available")
    hits, text = _words_in_order(model, path)
    assert hits >= 6, f"control phrase: {hits}/7; heard {text!r}"


# ── lyrics → notes (no audio) ────────────────────────────────────────────────

LYRICS = """[Verse 1]
I walked the city when the lights went down
Every window glowing like a golden crown
You were waiting where the river bends
Telling me the night would never end

[Chorus]
Hold me closer, don't let go
Take my hand and dance real slow
Hold me closer, don't let go
Stay with me until the morning glow
"""


def test_the_phrase_lands_one_syllable_per_note():
    score = _phrase_score()
    assert [n.syllable for n in score] == WORDS
    assert [n.midi for n in score] == MIDI


def _sung_by_section(bp, seed=0):
    from auralis.composer.arrange import arrange
    from auralis.voice.guide import build_score

    arr = arrange(bp, seed=seed)
    score = build_score(bp, arr["tracks"]["melody"], arr.get("melody_lyrics"))
    spb = 60.0 / bp["tempo"]
    out = []
    for s in bp["sections"]:
        a, b = (s["start_bar"] - 1) * 4 * spb, (s["start_bar"] - 1 + s["bars"]) * 4 * spb
        out.append((s, [n for n in score if a - 1e-3 <= n.start < b - 1e-3]))   # starts are rounded to 0.1 ms
    return out


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_each_lyric_line_is_sung_once_in_order(seed):
    """Every entered line is sung in full, once, in its order (per section):
    no missing words, no repeats, no extra syllables (melody v2)."""
    from auralis.composer.blueprint import build_blueprint
    from auralis.voice.guide import lyric_lines, syllabify

    bp = build_blueprint("slow 90s R&B ballad", LYRICS, seed=seed)
    assert bp["melody_version"] == 3
    checked = 0
    for s, notes in _sung_by_section(bp, seed):
        lines = lyric_lines(s)
        if not lines:
            assert all(not n.syllable for n in notes), "a section without lyrics must not invent words"
            continue
        sung = [n.syllable for n in notes]
        wanted = [syl for line in lines for syl in syllabify(line)]
        assert sung == wanted, f"{s['type']}: sang {len(sung)} syllables for {len(wanted)} written"
        ends = [i for i, n in enumerate(notes) if n.phrase_end]
        assert len(ends) == len(lines), "one phrase end per line (breath after each line)"
        assert all(a.start + a.duration <= b.start + 1e-6 for a, b in zip(notes, notes[1:])), "notes overlap"
        checked += 1
    assert checked >= 2


DENSE_LINE = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"
MANY_LINES = NL.join(f"line {w} goes on and on and on tonight" for w in "abcdefghijklmnop")


@pytest.mark.parametrize("lyrics", [DENSE_LINE, MANY_LINES, "just two words" + NL + "and a few more"],
                         ids=["15-syllable line", "16 dense lines", "2 sparse lines"])
def test_dense_and_sparse_sections_keep_every_syllable(lyrics):
    """No 14-syllable cap, no truncation when lines are many, no padding when they are few."""
    from auralis.composer.blueprint import build_blueprint
    from auralis.voice.guide import syllabify

    bp = build_blueprint("ballad", "[Verse]" + NL + lyrics, seed=0)
    found = False
    for s, notes in _sung_by_section(bp):
        if s.get("lyrics"):
            found = True
            assert [n.syllable for n in notes] == [x for line in s["lyrics"] for x in syllabify(line)]
            section_end = (s["start_bar"] - 1 + s["bars"]) * 4 * 60 / bp["tempo"]
            assert notes[-1].start + notes[-1].duration <= section_end + 1e-6
    assert found


def test_repeated_chorus_lines_reuse_the_hook_with_exact_counts():
    from auralis.composer.blueprint import build_blueprint

    bp = build_blueprint("ballad", LYRICS, seed=0)
    choruses = [notes for s, notes in _sung_by_section(bp) if s["type"] == "chorus" and notes]
    first = choruses[0]
    # lines 1 and 3 are the same words: same melody shape, shifted in time
    by_line, cur = [], []
    for n in first:
        cur.append(n)
        if n.phrase_end:
            by_line.append(cur)
            cur = []
    assert [n.syllable for n in by_line[0]] == [n.syllable for n in by_line[2]]
    assert [n.midi for n in by_line[0]] == [n.midi for n in by_line[2]]


def test_saved_v1_songs_render_exactly_as_before():
    """A blueprint saved before melody v2 (no `melody_version`) keeps its melody,
    its guide score and every other track, byte for byte (fingerprints taken
    from the pre-v2 code, Session 025)."""
    import hashlib
    import json
    from pathlib import Path

    from auralis.composer.arrange import arrange
    from auralis.voice.guide import build_score

    bp = json.loads((Path(__file__).parent / "fixtures_legacy_blueprint.json").read_text())
    assert "melody_version" not in bp
    arr = arrange(bp, seed=0)
    score = build_score(bp, arr["tracks"]["melody"], arr.get("melody_lyrics"))
    h = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()[:16]
    assert arr["melody_version"] == 1 and arr["melody_lyrics"] is None
    assert h(arr["tracks"]["melody"]) == "fd9dbdea0e9cf4c0"
    v1_fields = ("start", "duration", "midi", "velocity", "syllable", "vowel", "onset", "phrase_end")
    assert h([{k: n.to_dict()[k] for k in v1_fields} for n in score]) == "de2e449f5f078ec9"
    assert all(n.word == "" and n.word_pos == 0 and n.word_len == 1 for n in score)   # v2-only fields stay default
    assert h({k: v for k, v in arr["tracks"].items() if k != "melody"}) == "b5015d6c97e385b1"


def test_v2_changes_only_the_melody_and_survives_revision():
    from auralis.composer.arrange import arrange
    from auralis.composer.blueprint import build_blueprint, revise

    bp = build_blueprint("ballad", LYRICS, seed=0)
    v1 = dict(bp)
    v1.pop("melody_version")
    a2, a1 = arrange(bp, seed=0), arrange(v1, seed=0)
    for k in a2["tracks"]:
        if k != "melody":
            assert a2["tracks"][k] == a1["tracks"][k], f"{k} changed with the melody version"
    assert revise(bp, {"tempo": bp["tempo"] + 4})["melody_version"] == 3


# ── melody v3: digits are sung as words (Session 030) ────────────────────────

@pytest.mark.parametrize("text,spoken", [
    ("24/7 I think of you", "twenty four seven I think of you"),
    ("I was 19 in 1999", "I was nineteen in nineteen ninety nine"),
    ("my 2nd chance", "my second chance"),
    ("back in '99", "back in ninety nine"),
    ("the 3rd time, 21st night", "the third time, twenty first night"),
    ("100 percent", "one hundred percent"),
    ("no numbers here", "no numbers here"),
])
def test_numbers_are_spelled_as_sung(text, spoken):
    from auralis.voice.guide import spell_numbers

    assert spell_numbers(text) == spoken


DIGIT_LYRICS = NL.join(["[Verse]", "24/7 I think of you", "I was 19 in 1999", "my 2nd chance",
                        "back in '99 we sang"])


def test_v3_sings_every_number_as_words():
    from auralis.composer.blueprint import build_blueprint
    from auralis.voice.guide import lyric_lines, spell_numbers, syllabify

    bp = build_blueprint("ballad", DIGIT_LYRICS, seed=0)
    assert bp["melody_version"] == 3
    for s, notes in _sung_by_section(bp):
        if s.get("lyrics"):
            wanted = [x for line in s["lyrics"] for x in syllabify(spell_numbers(line))]
            assert [n.syllable for n in notes] == wanted
            assert "nineteen" in [n.word for n in notes] and "seven" in [n.word for n in notes]
            assert len(lyric_lines(s, spell=True)) == 4


def test_saved_v2_songs_with_numbers_render_exactly_as_before():
    """A v2 blueprint (saved Oct 13-17) keeps its tune and words; fingerprints taken
    with the published v2 code (13f9fed), Session 030. v2 dropped the digits."""
    import hashlib
    import json
    from pathlib import Path

    from auralis.composer.arrange import arrange
    from auralis.voice.guide import build_score

    bp = json.loads((Path(__file__).parent / "fixtures_v2_digits_blueprint.json").read_text(encoding="utf-8"))
    assert bp["melody_version"] == 2
    arr = arrange(bp, seed=0)
    score = build_score(bp, arr["tracks"]["melody"], arr.get("melody_lyrics"))
    h = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()[:16]
    fields = ("start", "duration", "midi", "velocity", "syllable", "vowel", "onset", "phrase_end")
    assert h(arr["tracks"]["melody"]) == "806eb59d6695a488"
    assert h([{k: n.to_dict()[k] for k in fields} for n in score]) == "d235f3d87f9c3d4b"
