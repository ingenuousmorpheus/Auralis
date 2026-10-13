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

@pytest.mark.xfail(strict=True, reason="Session 024: the vocalise guide sings vowels, not words (0/7 measured). "
                                       "Needs a lyric-capable guide singer; see AURALIS_SESSION.md Session 024.")
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


@pytest.mark.xfail(strict=True, reason="Session 024: with more melody phrases than lyric lines, build_score loops "
                                       "the lines and a repeated chorus hook has the wrong note count, so lines "
                                       "are repeated out of order or cut short.")
def test_each_lyric_line_is_sung_once_in_order():
    """Every entered line must be sung in full, once, in its order (per section)."""
    from auralis.composer.arrange import arrange
    from auralis.composer.blueprint import build_blueprint
    from auralis.voice.guide import build_score, syllabify

    bp = build_blueprint("slow 90s R&B ballad", LYRICS, seed=0)
    score = build_score(bp, arrange(bp, seed=0)["tracks"]["melody"])
    spb = 60.0 / bp["tempo"]
    for s in bp["sections"]:
        lines = s.get("lyrics") or []
        if not lines:
            continue
        a, b = (s["start_bar"] - 1) * 4 * spb, (s["start_bar"] - 1 + s["bars"]) * 4 * spb
        sung = [n.syllable for n in score if a <= n.start < b and n.syllable]
        wanted = [syl for line in lines for syl in syllabify(line)]
        assert sung == wanted, f"{s['type']}: sang {len(sung)} syllables for {len(wanted)} written"
