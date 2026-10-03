# Harmonic Reference

Auralis already matches a reference track's **frequency spectrum** — point it at
a song you like and Matchering retunes your EQ, loudness and width toward it.

Harmonic Reference is the same idea one axis over. Point it at a reference and
it reports what **notes** to change: key, mode, which scale degrees you lean on,
notes sitting outside the key, and how your melody's register compares.

It is deterministic DSP, like the rest of the engine. No model, no LLM.

## Why it compares scale degrees, not pitches

This is the decision the whole feature rests on.

A song in F minor and a song in C minor share almost no absolute pitches, yet
may be harmonically identical. Comparing raw pitch classes would report a huge
difference that means nothing musically.

So before anything is compared, each track's pitch-class energy is rotated so
index 0 is **that track's own tonic**. Both tracks are then described in scale
degrees — `1 ♭2 2 ♭3 3 4 ♭5 5 ♭6 6 ♭7 7` — and the comparison asks the question
a musician would: *how much do you lean on the ♭3 versus the 5, compared to the
reference?*

Degree deltas are the note-domain equivalent of per-band EQ deltas in a
mastering match.

## What it reports

| Kind | What it tells you |
|---|---|
| `transpose` | Semitones to move your track onto the reference's tonic. Always the shorter direction (`-5`, not `+7`), with the alternative listed — the two land on the same pitch class but only one keeps your register. |
| `mode` | Major/minor mismatch. Called out **separately from pitch** because C major and C minor share a tonic: no transposition reconciles them, you have to re-voice the 3rd. |
| `degree` | Which scale degrees you over- or under-use versus the reference, as a share of tonal energy. Ranked biggest-problem-first, capped at four. |
| `out_of_key` | Notes outside the detected key, with timecodes and the nearest in-key target. |
| `register` | Octave displacement between the two melodies. |
| `confidence` | Fires when key detection on either track is weak, so provisional results aren't read as certain. |

## Using it

### In the app

Sidebar tools → **Harmonic reference**. Choose your track and a reference, leave
both keys on `auto` (or type one like `F# minor`), and press *Compare harmony*.
A key that can't be read is refused straight away, before any analysis runs. The readout is three parts:

1. **Key cards + transposition** — both keys side by side with the semitone move
   between them, and each key's detection confidence.
2. **Degree chart** — twelve paired bars, you against the reference, drawn
   deliberately like a per-band EQ match because that is what it is. Pink means
   you use that degree more; blue means the reference does. Numbers underneath
   are percentage points of tonal energy.
3. **Suggestions + stray notes** — the written advice, severity-coded, and any
   out-of-key notes with timecodes so you can find them in the session.

### Over HTTP

```
POST /harmony/compare
  target=@my_mix.wav
  reference=@song_i_like.wav
  target_key=auto          # or "F minor"
  reference_key=auto
→ { "job_id": "...", "status": "started" }
  # 422 for an unreadable key, 415 for an unsupported file type (no job is created)

GET  /jobs/{job_id}              # poll — same job shape as every other stage
GET  /harmony/{job_id}/report    # the JSON report
```

Both files live only in that job's working directory and are discarded with it.
Neither is copied into any output — the same handling the mastering reference
already gets.

From Python:

```python
from auralis.engine.harmony import compare_to_reference, comparison_to_dict

comparison = compare_to_reference(mix, mix_sr, reference, reference_sr)
for suggestion in comparison.suggestions:
    print(suggestion.severity, suggestion.message)
```

## Accuracy and limits

- **Give it an instrumental or a full mix, not a bare vocal.** Key detection
  needs harmonic context; a naked vocal often cannot distinguish related keys.
  A weak detection is reported rather than hidden, but a good input is better
  than a warning.
- **Percussion is removed before chroma analysis.** Drums smear energy across
  every pitch class; without that step a busy track reads as "uses all twelve
  notes equally" and every comparison flattens out.
- **One key per track.** Songs that modulate are described by their dominant
  key. Chord-track analysis is the natural next step and is listed in the
  roadmap alongside the same gap in Pitch Polish.
- **Out-of-key does not mean wrong.** Blue notes, borrowed chords and passing
  tones are deliberate. The report flags them and says so; it does not correct
  anything. Pitch Polish is the stage that changes audio — this one only
  advises.
- **Note detection is monophonic** and capped at 90 seconds, chroma at 120.
  Both figures are statistical; they do not improve materially past that.
- **Notes come from Pitch Polish's tracker** (`voice/pitch._track_pitch` +
  `_segment_notes`), so both stages read the same notes. A legato step of one
  semitone with no gap can merge two notes into one (E→F reads as one note
  near F); the degree chart still shows that energy, so the imbalance is
  reported even when the stray-note list misses it.

## Relationship to the rest of Auralis

- Key detection and note tracking are imported from `voice/pitch.py` rather
  than reimplemented, so a track never reports one key (or one set of notes) in
  Pitch Polish and a different one here.
- Harmonic Reference **advises**; Pitch Polish **acts**. Reading the report and
  then running Pitch Polish with an explicit `key` is the intended path.
- `engine/harmony.py` has no dependency on the API or frontend, matching the
  rest of the engine package.
