"""Session 025: the experimental word guide, melody-targeted pitch, and honest notices.

Words are judged by the cached local faster-whisper ``base`` model, pitch by
pyin against the *written* melody (not the key). Tests that need Windows speech
or the recogniser skip cleanly where those are missing. The live Seed-VC test
runs only when AURALIS_LIVE_VOICE names a saved voice (read-only use).
Lyrics here are invented; no user material.
"""
from __future__ import annotations

import difflib
import os
import sys
from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

NL = chr(10)
VERSE_CHORUS = NL.join([
    "[Verse 1]",
    "I walked the city when the lights went down",
    "Every window glowing like a golden crown",
    "You were waiting where the river bends",
    "Telling me the night would never end",
    "",
    "[Chorus]",
    "Hold me closer, don't let go",
    "Take my hand and dance real slow",
    "Hold me closer, don't let go",
    "Stay with me until the morning glow",
])


def _words(text: str) -> list[str]:
    return "".join(c if c.isalpha() or c in " '" else " " for c in text.lower()).split()


def _word_guide():
    if sys.platform != "win32":
        pytest.skip("the word guide uses Windows speech voices")
    from auralis.models import MODELS

    guide = MODELS.get("word-guide")
    if not guide.is_installed():
        pytest.skip("no Windows speech voice on this computer")
    return guide


def _recogniser():
    fw = pytest.importorskip("faster_whisper")
    try:
        return fw.WhisperModel("base", device="cpu", compute_type="int8", local_files_only=True)
    except Exception as exc:
        pytest.skip(f"local faster-whisper 'base' model not available: {exc}")


def _recall(model, path, words) -> tuple[float, str]:
    segments, _ = model.transcribe(path, language="en", beam_size=5, temperature=0.0,
                                   condition_on_previous_text=False, vad_filter=False)
    text = " ".join(s.text.strip() for s in segments)
    matcher = difflib.SequenceMatcher(a=words, b=_words(text), autojunk=False)
    return sum(b.size for b in matcher.get_matching_blocks()) / len(words), text


def _melody_accuracy(audio, sr, score) -> float:
    """Share of written notes sung within 25 cents (octave slips of the tracker ignored)."""
    from auralis.voice.pitch import _score_accuracy

    return _score_accuracy(np.asarray(audio, np.float32), sr, score)["within_25_cents_pct"]


def _verse_chorus_score():
    from auralis.composer.arrange import arrange
    from auralis.composer.blueprint import build_blueprint
    from auralis.voice.guide import build_score

    bp = build_blueprint("slow 90s R&B ballad", VERSE_CHORUS, seed=0, key="D major", voice_range=(50, 72))
    arr = arrange(bp, seed=0)
    score = [n for n in build_score(bp, arr["tracks"]["melody"], arr.get("melody_lyrics")) if n.syllable]
    t0 = score[0].start - 0.6
    return [replace(n, start=round(n.start - t0, 4)) for n in score]


# ── the word guide ───────────────────────────────────────────────────────────

def test_word_guide_sings_a_short_phrase(tmp_path):
    from test_lyric_intelligibility import PHRASE, _phrase_score

    guide, model = _word_guide(), _recogniser()
    score = _phrase_score()
    audio = guide.sing(score, score[-1].start + score[-1].duration + 1.0)
    path = str(tmp_path / "phrase.wav")
    sf.write(path, audio, 44100)
    recall, text = _recall(model, path, PHRASE.split())
    assert recall >= 6 / 7, f"heard {text!r}"
    assert _melody_accuracy(audio, 44100, score) >= 85


def test_word_guide_sings_a_whole_verse_and_chorus(tmp_path):
    """56 words over 71 notes from the real composer (melody v2): the words in order
    and the written melody, both."""
    guide, model = _word_guide(), _recogniser()
    score = _verse_chorus_score()
    audio = guide.sing(score, score[-1].start + score[-1].duration + 1.0)
    path = str(tmp_path / "verse_chorus.wav")
    sf.write(path, audio, 44100)
    words = _words(" ".join(line for line in VERSE_CHORUS.splitlines() if line and not line.startswith("[")))
    recall, text = _recall(model, path, words)
    assert recall >= 0.85, f"{recall:.0%} of {len(words)} words in order; heard {text[:120]!r}"
    accuracy = _melody_accuracy(audio, 44100, score)
    assert accuracy >= 90, f"only {accuracy}% of notes within 25 cents of the written melody"


def test_word_guide_keeps_wordless_notes_audible():
    """Ad-libs and wordless sections have no words: they are vocalised, not dropped."""
    from test_lyric_intelligibility import _phrase_score

    guide = _word_guide()
    score = [replace(n, syllable="", word="") for n in _phrase_score()]
    audio = guide.sing(score, score[-1].start + score[-1].duration + 1.0)
    assert float(np.sqrt(np.mean(audio ** 2))) > 0.01


def test_weak_forms_are_respelled_for_the_speech_voice_only():
    from auralis.voice.word_singer import tts_text

    assert tts_text("the", "night") == "thuh" and tts_text("the", "end") == "thee"
    assert tts_text("a", "golden") == "uh" and tts_text("hold", "me") == "hold"


# ── melody-targeted pitch ────────────────────────────────────────────────────

def test_pitch_to_score_tunes_to_the_written_notes_and_keeps_vowels(tmp_path):
    """Notes sung 60–140 cents off (some towards a neighbouring scale tone, where key
    snapping would choose the wrong note) come back to the written melody; the vowel
    envelope and the consonant band survive."""
    import librosa

    from auralis.voice.pitch import _score_accuracy, pitch_to_score
    from auralis.voice.singing_provider import VocaliseSinger
    from test_lyric_intelligibility import _phrase_score

    score = _phrase_score()
    offsets = [0.6, -0.9, 1.2, -0.7, 1.4, 0.8, -1.1]                  # semitones off the written notes
    total = score[-1].start + score[-1].duration + 1.0
    # each note sung on its own and shifted off its written pitch, then spliced
    parts = np.zeros(int((total + 1.0) * 44100), np.float32)
    for n, off in zip(score, offsets):
        y = VocaliseSinger().sing([n], total, seed=1)
        a, b = int(n.start * 44100), int((n.start + n.duration) * 44100)
        seg = librosa.effects.pitch_shift(y[a:b], sr=44100, n_steps=off)
        parts[a:b] += seg[: b - a]
    src = str(tmp_path / "detuned.wav")
    sf.write(src, parts, 44100)
    before = _score_accuracy(parts, 44100, score)
    out = str(tmp_path / "tuned.wav")
    report = pitch_to_score(src, out, score)
    assert before["within_25_cents_pct"] < 30
    assert report["after"]["within_25_cents_pct"] >= 85, report["after"]
    assert report["after"]["median_abs_cents"] <= 20
    tuned, _ = sf.read(out)
    # vowels: the spectral envelope (MFCC 1-12) of each note stays close
    for n in score:
        a, b = int((n.start + 0.1 * n.duration) * 44100), int((n.start + 0.9 * n.duration) * 44100)
        m0 = librosa.feature.mfcc(y=parts[a:b].astype(np.float32), sr=44100, n_mfcc=13)[1:].mean(axis=1)
        m1 = librosa.feature.mfcc(y=tuned[a:b].astype(np.float32), sr=44100, n_mfcc=13)[1:].mean(axis=1)
        assert np.corrcoef(m0, m1)[0, 1] > 0.9, f"{n.syllable!r}: vowel envelope changed"


def test_pitch_to_score_keeps_the_words(tmp_path):
    """Score tuning must not cost intelligibility: words recognised after ≥ before."""
    from auralis.voice.pitch import pitch_to_score

    guide, model = _word_guide(), _recogniser()
    score = _verse_chorus_score()[:24]                                  # the first three lines
    audio = guide.sing(score, score[-1].start + score[-1].duration + 1.0)
    src, out = str(tmp_path / "guide.wav"), str(tmp_path / "tuned.wav")
    sf.write(src, audio, 44100)
    pitch_to_score(src, out, score)
    words = _words("I walked the city when the lights went down Every window glowing like a golden crown "
                   "You were waiting where the river bends")
    before, _ = _recall(model, src, words)
    after, text = _recall(model, out, words)
    assert after >= before - 0.05, f"{before:.0%} → {after:.0%}; heard {text!r}"


# ── the pipeline and the notices ─────────────────────────────────────────────

def _sing(tmp_path, singer, production="lead"):
    import shutil

    from auralis.voice import VoiceProfileStore
    from auralis.voice.full_song import sing_song
    from test_full_song import _short

    bp = _short()
    ref = tmp_path / "ref.wav"
    sf.write(ref, (0.2 * np.sin(2 * np.pi * 220 * np.arange(44100 * 8) / 44100)).astype(np.float32), 44100)
    profile = VoiceProfileStore(tmp_path / "v").create("Stand In", str(ref), True)
    return sing_song(bp, None, profile, str(tmp_path / "song"), lambda s, d, q: shutil.copyfile(s, d),
                     quality="fast", production=production, master=False, singer=singer)


def test_wordless_guide_is_never_presented_as_singing_the_lyrics(tmp_path):
    from auralis.models import MODELS

    out = _sing(tmp_path, MODELS.get("vocalise"))
    assert out["guide_sings_words"] is False and out["guide_singer"] == "vocalise"
    assert "does not sing the words" in out["guide_notice"]
    assert out["pitch_mode"] == "key" and out["personal_use_only"] is False
    assert out["melody_version"] == 3


def test_word_guide_songs_are_tuned_to_the_melody_and_marked_personal_use(tmp_path):
    out = _sing(tmp_path, _word_guide())
    assert out["guide_sings_words"] is True and out["guide_singer"] == "word-guide"
    assert out["pitch_mode"] == "score" and out["pitch_accuracy"]["within_25_cents_pct"] >= 85
    assert out["personal_use_only"] is True and "Personal, local use only" in out["guide_notice"]


def test_word_sung_backing_parts_are_tuned_to_their_own_notes(tmp_path):
    """Doubles and harmonies sung with words drift like the lead; each is tuned to its
    own written notes (Session 031). Vocalise backing parts keep their old path."""
    from auralis.models import MODELS

    out = _sing(tmp_path, _word_guide(), production="full")
    acc = out["backing_pitch_accuracy"]
    assert set(acc) == set(out["backing_stems"]) and acc, out["backing_stems"]
    for part, a in acc.items():
        # ad-libs are fast wordless runs (~0.15 s notes): pitch tracking on them is noisy
        # (measured 80-100% across blueprints); word-sung parts measured 100% (Session 031)
        assert a["within_25_cents_pct"] >= (70 if part == "adlibs" else 85), (part, a)
    hum = _sing(tmp_path / "v", MODELS.get("vocalise"), production="full")
    assert "backing_pitch_accuracy" not in hum and hum["backing_stems"]


def test_the_guide_notice_travels_into_the_project(tmp_path):
    from auralis.composer.assemble import save_song_to_project
    from auralis.models import MODELS
    from auralis.projects import ProjectStore
    from test_full_song import _short

    song = _sing(tmp_path, MODELS.get("vocalise"))
    store = ProjectStore(tmp_path / "projects")
    saved = save_song_to_project(store, "Notice test", _short(), {"stems": {}}, song)
    lead = next(a for a in store.get(saved["project_id"]).assets if a.metadata.get("part") == "lead_vocal")
    assert lead.metadata["guide_singer"] == "vocalise" and "does not sing the words" in lead.metadata["guide_notice"]


def test_api_refuses_an_unknown_or_wrong_kind_guide_before_starting():
    from fastapi.testclient import TestClient

    from auralis.api import main
    from test_full_song import _short

    client = TestClient(main.app)
    body = {"blueprint": _short(), "profile_id": "nobody", "guide_singer": "no-such-singer"}
    assert client.post("/composer/sing", json=body).status_code == 422
    assert client.post("/composer/sing", json={**body, "guide_singer": "seed-vc"}).status_code == 422
    models = client.get("/models").json()
    word = next(m for m in models["models"] if m["id"] == "word-guide")
    assert word["experimental"] is True and word["kind"] == "guide_singer"
    assert {"vocalise", "word-guide"} <= set(models["kinds"]["guide_singer"]["options"])


# ── the default (owner-approved, Session 032) ─────────────────────────────────

def _registry(tmp_path, config=None, word_installed=True):
    import json

    from auralis.models.builtin import VocaliseGuide, WordGuide
    from auralis.models.lifecycle import ModelManager
    from auralis.models.registry import Registry

    class Word(WordGuide):
        def is_installed(self):
            return word_installed

    path = tmp_path / "models.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if config is not None:
        path.write_text(json.dumps(config), "utf-8")
    return Registry(ModelManager(), config_path=path, providers=(VocaliseGuide(), Word()))


def test_the_word_guide_is_the_default_where_it_can_run(tmp_path):
    reg = _registry(tmp_path)
    assert reg.guide_singer().spec.id == "word-guide"
    spare = _registry(tmp_path / "x", word_installed=False)
    model, why = spare.resolve("guide_singer")
    assert model.spec.id == "vocalise" and "isn't available here" in why


def test_settings_saved_before_the_word_guide_get_the_new_default_once(tmp_path):
    """'vocalise' in settings written before Session 025 was the only option, not a choice."""
    from auralis.models.registry import GUIDE_CHOICE_MARK

    old = _registry(tmp_path / "a", {"choices": {"guide_singer": "vocalise"}, "policy": "balanced"})
    assert old.guide_singer().spec.id == "word-guide"
    chose = _registry(tmp_path / "b", {"choices": {"guide_singer": "vocalise"}, GUIDE_CHOICE_MARK: True})
    assert chose.guide_singer().spec.id == "vocalise"                 # a real choice is respected
    reg = _registry(tmp_path / "c")
    reg.select("guide_singer", "vocalise")
    again = _registry(tmp_path / "c")
    assert again.guide_singer().spec.id == "vocalise"                  # and stays respected after saving


# ── live: consonants through Seed-VC (opt-in, read-only use of a saved voice) ──

@pytest.mark.skipif(not os.environ.get("AURALIS_LIVE_VOICE"), reason="set AURALIS_LIVE_VOICE to a saved voice name")
def test_live_words_survive_voice_conversion(tmp_path):
    from auralis.voice.profiles import VoiceProfileStore
    from auralis.voice.seed_vc import SeedVCProvider
    from test_lyric_intelligibility import PHRASE, _phrase_score

    guide, model = _word_guide(), _recogniser()
    profile = next(p for p in VoiceProfileStore().list() if p.name == os.environ["AURALIS_LIVE_VOICE"])
    score = _phrase_score()
    src, out = str(tmp_path / "guide.wav"), str(tmp_path / "converted.wav")
    sf.write(src, guide.sing(score, score[-1].start + score[-1].duration + 1.0), 44100)
    SeedVCProvider().convert(src, profile.reference_path, out, quality="studio",
                             checkpoint_path=profile.checkpoint_path, config_path=profile.config_path)
    before, _ = _recall(model, src, PHRASE.split())
    after, text = _recall(model, out, PHRASE.split())
    assert after >= before - 1 / 7, f"{before:.0%} → {after:.0%}; heard {text!r}"
