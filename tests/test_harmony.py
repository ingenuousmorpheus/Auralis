"""Tests for Harmonic Reference (reference matching in the note domain).

The property that carries the whole feature is that comparison happens in
SCALE DEGREES relative to each track's own tonic. If that regresses, two
harmonically identical songs in different keys would report as wildly
different and every suggestion downstream becomes noise — so it gets pinned
hardest here.
"""
import numpy as np
import pytest

from auralis.engine.harmony import (
    DEGREE_NAMES,
    analyse_harmony,
    compare_to_reference,
    comparison_to_dict,
    _shortest_transpose,
)
from auralis.voice.pitch import parse_key

SR = 22050


def tone(midi, seconds, sr=SR, amp=0.12):
    import librosa
    t = np.arange(int(sr * seconds)) / sr
    freq = librosa.midi_to_hz(midi)
    env = np.minimum(t / 0.03, 1.0) * np.minimum((seconds - t) / 0.05, 1.0)
    # A couple of harmonics so chroma_cqt sees a pitched tone, not a bare sine.
    wave = (np.sin(2 * np.pi * freq * t)
            + 0.35 * np.sin(4 * np.pi * freq * t)
            + 0.18 * np.sin(6 * np.pi * freq * t))
    return (amp * wave * env).astype(np.float32)


def progression(midis, seconds=0.55):
    """A simple melody over the given MIDI notes."""
    return np.concatenate([tone(m, seconds) for m in midis]).astype(np.float32)


# ── the load-bearing property ────────────────────────────────────────────────

def test_same_music_in_different_keys_compares_as_similar():
    """C major and F major versions of the SAME melody must look alike.

    They share almost no absolute pitch classes. Only degree-relative
    comparison can see that they are the same music.
    """
    c_major = progression([60, 62, 64, 65, 67, 64, 60])          # 1 2 3 4 5 3 1
    f_major = progression([65, 67, 69, 70, 72, 69, 65])          # same degrees

    result = compare_to_reference(
        c_major, SR, f_major, SR,
        target_key=parse_key("C major"),
        reference_key=parse_key("F major"),
    )
    # Degree profiles should line up closely even though the pitches don't.
    worst_degree_gap = max(abs(d) for d in result.degree_deltas)
    assert worst_degree_gap < 0.12, (
        f"same melody in two keys reported degree gap {worst_degree_gap:.3f}; "
        "degree normalisation is probably broken"
    )
    # And the raw pitch-class profiles genuinely DO differ — proving the test
    # above is meaningful rather than trivially true.
    raw_gap = max(
        abs(t - r) for t, r in zip(result.target.chroma, result.reference.chroma)
    )
    assert raw_gap > worst_degree_gap


def test_transpose_suggestion_points_from_target_to_reference():
    c = progression([60, 64, 67, 60])
    d = progression([62, 66, 69, 62])
    result = compare_to_reference(
        c, SR, d, SR,
        target_key=parse_key("C major"), reference_key=parse_key("D major"),
    )
    assert result.suggested_transpose == 2
    top = [s for s in result.suggestions if s.kind == "transpose"][0]
    assert top.severity == "high"
    assert "C major" in top.message and "D major" in top.message


@pytest.mark.parametrize("frm,to,expected", [
    (0, 0, 0),
    (0, 2, 2),
    (0, 7, -5),     # up a fifth == down a fourth; take the gentler move
    (0, 6, 6),      # tritone: exactly 6, stays positive
    (7, 0, 5),
    (0, 11, -1),
    (11, 0, 1),
])
def test_shortest_transpose_takes_the_gentler_direction(frm, to, expected):
    assert _shortest_transpose(frm, to) == expected


def test_no_transposition_reported_when_keys_match():
    a = progression([60, 64, 67, 72])
    b = progression([60, 65, 67, 72])
    result = compare_to_reference(
        a, SR, b, SR,
        target_key=parse_key("C major"), reference_key=parse_key("C major"),
    )
    assert result.suggested_transpose == 0
    top = [s for s in result.suggestions if s.kind == "transpose"][0]
    assert top.severity == "low"


# ── mode is not a transposition ──────────────────────────────────────────────

def test_mode_mismatch_is_reported_separately_from_pitch():
    """C major vs C minor share a tonic — a transpose can't reconcile them."""
    major = progression([60, 64, 67, 72])
    minor = progression([60, 63, 67, 72])
    result = compare_to_reference(
        major, SR, minor, SR,
        target_key=parse_key("C major"), reference_key=parse_key("C minor"),
    )
    assert result.suggested_transpose == 0
    modes = [s for s in result.suggestions if s.kind == "mode"]
    assert modes, "a major/minor mismatch must be surfaced"
    assert modes[0].severity == "high"
    assert "transposing won't" in modes[0].message.lower()


# ── degree balance ───────────────────────────────────────────────────────────

def test_degree_imbalance_is_detected_and_named():
    """Hammering the 3rd against a reference that favours the 5th."""
    heavy_third = progression([64] * 6 + [60])
    heavy_fifth = progression([67] * 6 + [60])
    result = compare_to_reference(
        heavy_third, SR, heavy_fifth, SR,
        target_key=parse_key("C major"), reference_key=parse_key("C major"),
    )
    degrees = [s for s in result.suggestions if s.kind == "degree"]
    assert degrees, "a clear degree imbalance should produce a suggestion"
    named = " ".join(s.detail["degree"] for s in degrees)
    assert "3" in named or "5" in named
    # Suggestions are ranked by magnitude, biggest problem first.
    magnitudes = [abs(s.detail["delta"]) for s in degrees]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_identical_tracks_produce_no_degree_complaints():
    melody = progression([60, 62, 64, 65, 67])
    result = compare_to_reference(
        melody, SR, melody.copy(), SR,
        target_key=parse_key("C major"), reference_key=parse_key("C major"),
    )
    assert result.suggested_transpose == 0
    assert not [s for s in result.suggestions if s.kind == "degree"], (
        "a track compared against itself must not be told to change notes"
    )


# ── stray notes ──────────────────────────────────────────────────────────────

def test_out_of_key_note_is_found_and_given_a_target():
    # F♯ (66) does not belong to C major.
    melody = progression([60, 62, 66, 65, 67], seconds=0.7)
    analysis = analyse_harmony(melody, SR, key_override=parse_key("C major"))
    assert analysis.note_count > 0
    strays = analysis.out_of_key_notes
    assert strays, "F# in C major should be flagged"
    stray = min(strays, key=lambda n: abs(n.detected_midi - 66))
    assert abs(stray.detected_midi - 66) < 1.0
    assert stray.nearest_in_key_midi in (65, 67)   # F or G
    assert stray.nearest_in_key_note.rstrip("0123456789-") in ("F", "G")


def test_in_key_melody_reports_no_strays():
    melody = progression([60, 62, 64, 65, 67], seconds=0.7)
    analysis = analyse_harmony(melody, SR, key_override=parse_key("C major"))
    assert analysis.out_of_key_notes == []


def test_out_of_key_suggestion_carries_timecodes():
    melody = progression([60, 66, 64], seconds=0.7)
    result = compare_to_reference(
        melody, SR, progression([60, 64, 67], seconds=0.7), SR,
        target_key=parse_key("C major"), reference_key=parse_key("C major"),
    )
    stray = [s for s in result.suggestions if s.kind == "out_of_key"]
    assert stray, "F# in C major should produce an out-of-key suggestion"
    assert "0:00.7" in stray[0].message, "stray notes must be locatable in time"
    assert "1 note sits" in stray[0].message
    assert stray[0].detail["total"] == 1


# ── register ─────────────────────────────────────────────────────────────────

def test_octave_displacement_is_reported():
    low = progression([48, 50, 52, 53], seconds=0.7)
    high = progression([72, 74, 76, 77], seconds=0.7)
    result = compare_to_reference(
        low, SR, high, SR,
        target_key=parse_key("C major"), reference_key=parse_key("C major"),
    )
    register = [s for s in result.suggestions if s.kind == "register"]
    assert register, "a two-octave gap should be reported"
    assert register[0].detail["semitones"] < 0


# ── report shape ─────────────────────────────────────────────────────────────

def test_comparison_serialises_for_the_api():
    a = progression([60, 64, 67])
    b = progression([62, 66, 69])
    result = compare_to_reference(
        a, SR, b, SR,
        target_key=parse_key("C major"), reference_key=parse_key("D major"),
    )
    payload = comparison_to_dict(result)
    assert payload["degree_names"] == DEGREE_NAMES
    assert len(payload["degree_deltas"]) == 12
    assert payload["suggested_transpose"] == 2
    assert payload["target"]["key_name"] == "C major"
    for suggestion in payload["suggestions"]:
        assert suggestion["kind"] and suggestion["message"]
        assert suggestion["severity"] in {"high", "medium", "low"}
    import json
    json.dumps(payload)   # must be JSON-safe for the API and report file


def test_degree_weights_are_a_distribution():
    analysis = analyse_harmony(progression([60, 64, 67]), SR,
                               key_override=parse_key("C major"))
    assert len(analysis.degree_weights) == 12
    assert abs(sum(analysis.degree_weights) - 1.0) < 0.01
    assert all(v >= 0 for v in analysis.degree_weights)


def test_short_input_is_rejected_clearly():
    with pytest.raises(ValueError, match="too short"):
        analyse_harmony(np.zeros(64, dtype=np.float32), SR)


# ── API ──────────────────────────────────────────────────────────────────────

def _wav(audio):
    import io
    import soundfile as sf
    buffer = io.BytesIO()
    sf.write(buffer, audio, SR, format="WAV")
    buffer.seek(0)
    return buffer


def _upload(client, target_key="auto", reference_key="auto", reference_name="r.wav"):
    return client.post(
        "/harmony/compare",
        files={
            "target": ("t.wav", _wav(progression([60, 64, 67, 60])), "audio/wav"),
            "reference": (reference_name, _wav(progression([62, 66, 69, 62])), "audio/wav"),
        },
        data={"target_key": target_key, "reference_key": reference_key},
    )


def test_api_compares_two_uploads_and_serves_the_report():
    import json
    import time

    from fastapi.testclient import TestClient

    from auralis.api import main

    client = TestClient(main.app)
    started = _upload(client, target_key="C major", reference_key=" Auto ")
    assert started.status_code == 200
    job_id = started.json()["job_id"]
    for _ in range(600):
        status = client.get(f"/jobs/{job_id}").json()
        if status["stage"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert status["stage"] == "done", status["error"]
    assert status["result"]["target"]["key_name"] == "C major"
    report = client.get(f"/harmony/{job_id}/report")
    assert report.status_code == 200
    assert json.loads(report.content)["degree_names"] == DEGREE_NAMES


def test_api_rejects_a_bad_key_or_file_type_before_starting_a_job():
    from fastapi.testclient import TestClient

    from auralis.api import main

    client = TestClient(main.app)
    jobs_before = len(main.JOBS)
    bad_key = _upload(client, reference_key="nonsense")
    assert bad_key.status_code == 422
    assert "Key must look like" in bad_key.json()["detail"]
    assert _upload(client, reference_name="r.txt").status_code == 415
    assert len(main.JOBS) == jobs_before
    assert client.get("/harmony/unknown/report").status_code == 404


def test_a_final_held_note_still_counts():
    """The last note runs to the end of the file with no silence after it."""
    import librosa
    t = np.arange(int(SR * 0.8)) / SR
    held = (0.12 * np.sin(2 * np.pi * librosa.midi_to_hz(66) * t)).astype(np.float32)
    melody = np.concatenate([progression([60, 64], seconds=0.7), held])
    analysis = analyse_harmony(melody, SR, key_override=parse_key("C major"))
    assert any(abs(n.detected_midi - 66) < 1.0 for n in analysis.out_of_key_notes), (
        "an F# held to the end of the take must still be flagged"
    )
