# Auralis Session — Artist-Native Song Creation Plan

**Created:** 2026-09-23  
**Repository:** `ingenuousmorpheus/Auralis`  
**Source of truth:** GitHub `main`  
**Current repo HEAD inspected:** `87704d5`  
**Goal:** Evolve Auralis from a local-first mixing/mastering + singing-voice workstation into a **private song-creation studio that can generate new songs from the user's own musical catalog and render the vocals in the user's own trained singing voice**.

---

# 0. Read This First

Auralis already has much more of the final system than a greenfield "Suno clone" would.

The current code already provides:

- local stereo mastering
- multi-stem mixing
- style/sound profiles
- reference-track tonal matching
- loudness and true-peak control
- a React/Vite studio UI
- FastAPI backend
- private voice profiles
- instant singing-voice conversion through the optional Seed-VC provider
- full Studio Voice datasets and resumable fine-tuning
- paired guide/real-vocal calibration
- vocal range/dataset analysis
- automatic pitch polish
- Vocal Finish / vocal-chain processing
- instrumental-aware vocal placement
- downloadable WAV outputs and reports

That means Auralis does **not** need to be rebuilt.

The missing layer is the part that creates the song **before** the existing mix / voice / mastering pipeline.

The target product is:

```text
MY MUSIC LIBRARY
      +
MY VOICE
      +
NEW IDEA / PROMPT / LYRICS
      ↓
AURALIS ARTIST DNA
      ↓
SONG COMPOSER
      ↓
ARRANGEMENT / INSTRUMENTAL
      ↓
GUIDE SINGER
      ↓
MY TRAINED VOICE
      ↓
PITCH + VOCAL FINISH
      ↓
MIX + MASTER
      ↓
FINISHED ORIGINAL SONG
```

This should feel like a **local Suno-style creation experience**, but personalized around the user's own catalog and own singing voice.

Do not throw away the deterministic DSP architecture. The generative layer should feed the existing Auralis engine, not replace it.

---

# 1. Current Architecture — What We Already Have

## Core audio engine — IMPLEMENTED

Existing modules:

```text
auralis/engine/analysis.py
auralis/engine/mixer.py
auralis/engine/mastering.py
auralis/engine/loudness.py
auralis/engine/pipeline.py
auralis/engine/profiles/
```

Strength:

Auralis already has the final-stage audio pipeline required to turn generated or imported material into a controlled mix/master.

Do not duplicate this functionality inside the future generator.

---

## Voice identity — IMPLEMENTED / STRONG FOUNDATION

Existing modules:

```text
auralis/voice/profiles.py
auralis/voice/seed_vc.py
auralis/voice/paired.py
auralis/voice/pitch.py
auralis/voice/finish.py
frontend/src/VoiceStudio.jsx
```

The current design already supports:

```text
clean reference
→ private voice profile
→ optional 10–45+ minute dataset
→ Seed-VC fine-tuning
→ guide vocal conversion
→ pitch polish
→ vocal finish
```

This is already close to the **Kits.ai-style voice portion** of the desired product.

The important missing capability is that Auralis currently expects the user to provide the **guide vocal**.

For full song generation, Auralis needs to create that guide automatically from:

```text
lyrics
+
melody
+
rhythm
+
phrasing
```

Then the existing Seed-VC pipeline can convert the generated guide into the user's voice.

---

# 2. Product Vision

The long-term home screen should offer five primary workflows:

```text
CREATE A SONG
Continue My Sound

CREATE FROM IDEA
Prompt → complete song

TURN DEMO INTO SONG
Voice memo / rough demo → arranged record

SING IN MY VOICE
Existing Voice Studio

MIX / MASTER
Existing Auralis workflows
```

The new flagship workflow is:

## "Create in My Sound"

User provides:

- a short description
- optional lyrics
- optional mood
- optional song length
- optional influence selection from their own songs

Example:

```text
"Dark late-night R&B.
92 BPM feeling.
Big chorus.
Make it feel related to my last three songs
without copying any of them."
```

Auralis then:

1. retrieves relevant traits from the user's music library
2. creates a song blueprint
3. generates harmony, melody, groove and arrangement
4. renders an instrumental
5. creates a guide vocal
6. converts it into the user's trained voice
7. performs pitch polish and vocal finishing
8. mixes the vocal into the instrumental
9. masters the final song

---

# 3. Artist DNA — The Critical New System

Do **not** fine-tune one giant model on the user's songs first.

V1 should build a transparent local **Artist DNA profile**.

Create:

```text
auralis/artist/
    library.py
    analyze.py
    dna.py
    retrieval.py
    similarity.py
```

Local data should live outside Git:

```text
%LOCALAPPDATA%/Auralis/artist/
    library/
    analyses/
    dna/
    generations/
```

## Import sources

Allow the user to import only material they own or are authorized to use:

- finished songs
- instrumentals
- stems
- demos
- MIDI
- lyrics/text
- project exports

Never commit the user's audio or trained voice files to GitHub.

The current `.gitignore` already excludes common audio formats and model weights. Preserve that rule.

## Extract musical traits

For each song analyze and store:

### Global

- BPM / tempo map
- key / mode
- duration
- loudness
- dynamic range
- stereo width

### Structure

- intro
- verse
- pre-chorus
- chorus
- bridge
- outro
- section lengths
- energy curve

### Harmony

- chord sequence
- chord rhythm
- harmonic tension
- common substitutions
- key-change behavior

### Melody

- vocal melody contour where available
- note range
- phrase length
- interval tendencies
- repetition patterns
- hook density

### Rhythm

- kick/snare patterns
- swing
- syncopation
- subdivision
- groove density

### Production

- instrumentation
- spectral balance
- bass character
- drum density
- ambience/reverb
- vocal-forwardness
- arrangement density

### Voice

Reuse the existing Voice Studio analysis:

- comfortable range
- trained range
- vocal textures represented in the dataset
- paired calibration coverage

The Artist DNA should be inspectable in the UI.

Example:

```text
MY ARTIST DNA

Primary tempos       78–96 BPM
Common keys          C#m · F#m · Am
Typical structure    Intro → V → PC → C → V → C → Bridge → C
Hook style           short repeated melodic phrases
Vocal range          A2–G4
Harmony density      medium
Drum character       sparse verses / dense chorus
Low end              warm
Stereo width         wide choruses
```

This makes the personalization explainable instead of mysterious.

---

# 4. Song Memory / Retrieval

Auralis should not simply mash together every song the user has made.

Build a local retrieval layer.

When a user enters a new song request:

```text
prompt
   ↓
Artist DNA
   ↓
retrieve 3–8 relevant songs/sections
   ↓
extract reusable CHARACTERISTICS
   ↓
Song Blueprint
```

Retrieve traits, not raw waveform chunks.

Examples:

```text
"Use the drum energy of Song A"
"Use the chorus lift behavior found in Songs B and D"
"Stay near the vocal range used in Song C"
```

Do not directly copy a melody or audio passage.

---

# 5. Song Blueprint Engine

Create:

```text
auralis/composer/
    brief.py
    blueprint.py
    harmony.py
    melody.py
    rhythm.py
    arrangement.py
    validation.py
```

The first generative output should **not** be audio.

It should be a structured, editable Song Blueprint.

Example:

```json
{
  "tempo": 88,
  "key": "F# minor",
  "meter": "4/4",
  "sections": [
    {"type":"intro","bars":4},
    {"type":"verse","bars":16},
    {"type":"prechorus","bars":8},
    {"type":"chorus","bars":16}
  ],
  "chords": {},
  "melody": {},
  "groove": {},
  "energy_curve": {},
  "instrumentation": []
}
```

Benefits:

- editable
- testable
- reproducible
- easier to regenerate one section
- can support multiple rendering engines later

The user should be able to regenerate:

```text
only chorus
only drums
only vocal melody
only bridge
only lyrics
```

without destroying the rest of the song.

---

# 6. Lyrics Layer

Create an optional lyrics module:

```text
auralis/composer/lyrics.py
```

It should support:

- user-written lyrics
- partially written lyrics
- prompt-generated original lyrics
- section-aware syllable counts
- rhyme targets
- phrase lengths matched to melody
- rewrite one line / one verse / one hook

Lyrics generation can use a local LLM through the existing local-first philosophy.

The LLM handles **language only**.

It does not directly process the waveform.

---

# 7. Music Generation / Rendering Layer

This is the largest missing system.

Create a provider abstraction rather than hard-coding one model:

```text
auralis/generation/
    base.py
    registry.py

    providers/
        midi_renderer.py
        local_audio_generator.py
```

Interface concept:

```python
render_song(blueprint, artist_context, seed)
render_section(section, context, seed)
render_instrument(role, section, context, seed)
```

## V1 — Structured / MIDI-first generation

Start here because it is controllable.

Generate:

- chords
- bass
- drums
- melodic parts
- MIDI arrangement
- automation/energy instructions

Render those through local instruments/samplers.

This also aligns with the existing `RECONSTRUCTION_ROADMAP.md` direction.

## V2 — Generative audio provider

Add an optional local music-generation model behind the provider interface.

It can render richer textures and atmospheric parts from:

```text
Song Blueprint
+
Artist DNA
+
section prompt
```

Do not make Auralis dependent on a single model.

Models will change quickly; the provider boundary should survive model replacements.

## Hybrid mode

The strongest eventual system is likely:

```text
structured composition
+
generated textures
+
real/user stems
+
Auralis mixing
```

rather than trying to ask one black-box model to create the entire record.

---

# 8. "Atmosphere" Generation

The user specifically wants a Suno-like atmosphere.

Treat **atmosphere** as its own production layer.

Create:

```text
auralis/generation/atmosphere.py
```

It can generate or assemble:

- pads
- drones
- transitions
- reverse textures
- risers
- room beds
- ambience
- vocal textures
- ear candy
- impact layers

Atmosphere should follow:

- key
- BPM
- song section
- energy curve
- Artist DNA

Example:

```text
Verse:
dark filtered pad
low room ambience
minimal ear candy

Pre-chorus:
rising harmonic texture
increased stereo width

Chorus:
wide pad
counter texture
impact
background vocal atmosphere
```

This provides the emotional "world" around the song without forcing the main composition model to do everything.

---

# 9. Automatic Guide Singer — Required for Full Song Creation

This is the bridge between the new composer and the existing Voice Studio.

Current system:

```text
human guide vocal
→ Seed-VC
→ user's voice
```

Required system:

```text
lyrics + melody + timing
→ synthetic guide singer
→ Seed-VC
→ user's voice
```

Create:

```text
auralis/voice/guide.py
auralis/voice/singing_provider.py
```

The guide singer does **not** need to sound like the user.

Its job is to accurately perform:

- phonemes
- pitch
- timing
- note lengths
- vibrato instructions
- dynamics
- breath placement
- phrasing

Then the existing private Studio Voice supplies identity/timbre.

This separation is important:

```text
COMPOSER decides WHAT is sung
GUIDE SINGER performs HOW it is sung
SEED-VC supplies WHO it sounds like
AURALIS finish makes it sound RECORD-READY
```

That is the core architecture needed to achieve the requested experience.

---

# 10. Vocal Production Stack

Reuse the existing pipeline.

Do not rebuild it.

Target:

```text
Guide singer
   ↓
Seed-VC / Studio Voice
   ↓
Pitch Polish
   ↓
Vocal Finish
   ↓
Doubles / harmonies
   ↓
Instrumental placement
   ↓
Mix engine
```

## New harmony / doubles generator

Add:

```text
auralis/voice/harmony.py
```

From the lead melody and chords:

- generate upper/lower harmonies
- create doubles
- create ad-lib suggestions
- render guides
- convert each through the user's voice profile
- vary timing/formant/dynamics slightly to avoid robotic stacking

User controls:

```text
Lead only
Lead + doubles
Lead + harmony
Full vocal production
```

---

# 11. Three Creation Modes

## Mode A — Continue My Sound

Input:

- idea/prompt
- select optional songs from My Music

Output:

- completely new song informed by Artist DNA

## Mode B — Build From My Demo

Input:

- voice memo
- rough piano/guitar
- rough beat
- unfinished song

Pipeline:

```text
analyze demo
→ infer tempo/key/chords/structure
→ preserve melody where requested
→ create arrangement
→ generate missing sections
→ voice render
→ mix/master
```

## Mode C — Generate Around My Lyrics

Input:

- lyrics

Auralis:

```text
analyzes syllables
→ proposes tempo/key
→ creates melody
→ builds chords
→ creates arrangement
→ guide singer
→ user's voice
→ finished song
```

---

# 12. Similarity / Originality Guard

Because Auralis learns from the user's own catalog, add a similarity check before final render.

Create:

```text
auralis/artist/similarity.py
```

Compare a generated song against the library for:

- melody overlap
- rhythmic overlap
- chord/structure overlap
- audio fingerprint similarity

If a generated section is excessively similar to an existing song, flag it and regenerate the section.

Goal:

```text
SOUNDS LIKE ME
≠
COPIES MY OLD SONG
```

---

# 13. New UI — Create Studio

Add a new top-level mode:

```text
CREATE
```

Proposed flow:

## Screen 1 — Idea

```text
What do you want to make?

[prompt]

Lyrics:
[write / paste / generate]

Use My Artist DNA      ON

Influence from my songs:
[automatic] [select]
```

## Screen 2 — Blueprint

Show:

- BPM
- key
- structure
- chords
- energy curve
- vocal range
- arrangement

Allow edits before expensive generation.

## Screen 3 — Generate

Visible stages:

```text
Understanding your catalog
Writing song blueprint
Composing harmony
Writing melody
Building arrangement
Creating atmosphere
Rendering instrumental
Creating guide vocal
Rendering your voice
Producing vocals
Mixing
Mastering
```

## Screen 4 — Studio

Stem view:

```text
Drums
Bass
Music
Atmosphere
Lead vocal
Doubles
Harmonies
FX
```

Buttons:

```text
Regenerate
Replace
Mute
Solo
Mix
Master
Export stems
Export song
```

---

# 14. Project / Session Persistence

Auralis currently uses per-job working files.

Full song creation requires persistent projects.

Create a local project structure:

```text
%LOCALAPPDATA%/Auralis/projects/<project-id>/

project.json
blueprint.json
lyrics.txt

sources/
generated/
stems/
vocals/
mixes/
masters/
reports/
```

Project JSON records:

- generator/provider versions
- random seeds
- selected Artist DNA snapshot
- prompts
- blueprint revisions
- voice profile ID
- all generated stems
- mix/master settings

Every generation should be reproducible where the provider permits deterministic seeds.

---

# 15. Provider Isolation

Follow the same philosophy already used by Seed-VC.

Large or differently licensed generators should **not** be copied into the core MIT package.

Use isolated providers under:

```text
%LOCALAPPDATA%/Auralis/providers/
```

Examples:

```text
seed-vc/
music-generator/
guide-singer/
instrument-renderer/
```

Auralis communicates through adapters.

This keeps:

- dependencies isolated
- licenses clear
- model swapping possible
- core Auralis maintainable

---

# 16. GPU Strategy

Do not load every model simultaneously.

Create a local model scheduler.

```text
COMPOSER / LLM
    unload
MUSIC GENERATOR
    unload
GUIDE SINGER
    unload
SEED-VC
    unload
DSP MIX/MASTER
```

Only one heavy model should own most VRAM at a time by default.

Support:

```text
GPU mode       maximum quality
Balanced       unload between stages
Low VRAM       CPU/offload where possible
```

This is especially important because the current Seed-VC provider already uses a CUDA-isolated environment.

---

# 17. Build Order

Do not attempt the entire "Suno" experience in one phase.

## AU-00 — Audit + Baseline

- run current Auralis
- run existing tests
- verify mastering
- verify stem mixing
- verify Voice Studio
- verify Seed-VC provider status
- confirm current v0.8 UI/code state
- document any README/version drift

**Gate:**

> Current Auralis behavior is preserved and reproducible before generative-song work begins.

---

## AU-01 — Persistent Projects

Build the project/session model.

**Gate:**

> A project can be created, closed, reopened, and all source/generated assets remain linked.

---

## AU-02 — My Music Library

Build local catalog import and analysis.

**Gate:**

> At least 10 user-owned songs can be imported and Auralis produces useful BPM/key/structure/harmony/energy metadata for each.

---

## AU-03 — Artist DNA V1

Aggregate library analysis into inspectable style tendencies.

**Gate:**

> The UI can describe recurring traits across the user's music without generating anything yet.

---

## AU-04 — Song Blueprint Generator

Prompt → structured song plan.

No expensive audio generation yet.

**Gate:**

> Auralis can create and edit a complete blueprint with tempo, key, sections, chords, arrangement and vocal-range constraints.

---

## AU-05 — MIDI / Structured Composer

Generate chords, bass, drums and melodic arrangement.

**Gate:**

> Auralis can render a complete instrumental from a blueprint using local instruments.

---

## AU-06 — Atmosphere Engine

Create section-aware textures and transitions.

**Gate:**

> A generated instrumental has musically appropriate atmosphere that follows key, tempo and section energy.

---

## AU-07 — Guide Singer

Lyrics + melody → synthetic guide vocal.

**Gate:**

> Given lyrics and the blueprint melody, Auralis renders a correctly timed/pitched dry guide vocal.

This is one of the most important gates in the roadmap.

---

## AU-08 — My Voice Full-Song Pipeline

Connect:

```text
Guide Singer
→ existing Seed-VC Studio Voice
→ existing Pitch Polish
→ existing Vocal Finish
```

**Gate:**

> Auralis can produce an entire lead vocal for an original generated song in the user's trained voice without requiring the user to sing the guide manually.

---

## AU-09 — Vocal Production

Add harmonies, doubles and ad-libs.

**Gate:**

> One generated song can produce lead, doubles and harmonies as separate stems.

---

## AU-10 — Automatic Song Assembly

Route generated stems through the existing mixer/mastering pipeline.

**Gate:**

> One prompt can travel end-to-end from blueprint to downloadable finished WAV while retaining editable stems.

---

## AU-11 — Generative Audio Provider

Add richer local audio generation behind the provider abstraction.

Do **not** remove the structured composer.

**Gate:**

> A section can be rendered by either the deterministic/structured path or an optional generative-audio provider using the same blueprint contract.

---

## AU-12 — Similarity Guard + Artist Retrieval

Add catalog retrieval and originality checks.

**Gate:**

> "Continue My Sound" retrieves useful characteristics from the user's catalog while flagging excessive melodic/audio similarity to prior songs.

---

## AU-13 — Demo-to-Song

Analyze a rough demo and build around it.

**Gate:**

> A phone-quality voice memo or rough instrumental can become a structured Auralis project with an arrangement that preserves the requested musical idea.

---

# 18. First Real Milestone

Do not wait for perfect Suno-like generation.

The first magical milestone is:

```text
10 of my songs imported
        ↓
Artist DNA built
        ↓
I type a song idea
        ↓
Auralis builds blueprint
        ↓
Auralis creates instrumental
        ↓
Auralis creates guide vocal
        ↓
Seed-VC turns it into MY voice
        ↓
Pitch Polish
        ↓
Vocal Finish
        ↓
Existing mixer/master
        ↓
FINISHED WAV
```

When that works once, improve quality rather than adding breadth.

---

# 19. What NOT To Do

Do not:

- replace the working DSP engine with a giant generative model
- rebuild Voice Studio from scratch
- give a text LLM raw waveform responsibilities
- hard-code the application around one music model
- keep all heavy GPU models loaded simultaneously
- commit user's songs, voice recordings, models or generated private audio to Git
- train on voices without the singer's permission
- directly copy passages from catalog songs
- build collaboration/cloud features before local end-to-end generation works

---

# 20. Immediate Next Engineering Task

The next coding session should work on **AU-00 only**.

Instructions:

1. Pull GitHub `main`.
2. Read this `auralissession.md` completely.
3. Inspect the actual current source.
4. Run the existing Python test suite.
5. Launch the current backend/frontend.
6. Verify:
   - master path
   - stem mix path
   - voice profile path
   - Seed-VC provider status
   - current Studio Voice UI
   - current pitch/finish APIs
7. Produce:

```text
docs/AURALIS_CURRENT_ARCHITECTURE.md
```

Map every existing endpoint/component/module that the new Create Studio will reuse.

Do not implement the generator during AU-00.

After AU-00 passes, begin **AU-01 Persistent Projects**.

---

# 21. Source-of-Truth Rule

GitHub `main` is the authoritative Auralis code and roadmap.

At the beginning of future Auralis work:

```text
FETCH/PULL SAFELY
→ READ auralissession.md
→ INSPECT ACTUAL CODE
→ WORK
```

At the end:

```text
TEST
→ UPDATE auralissession.md
→ REVIEW DIFF
→ COMMIT
→ PUSH
→ VERIFY
```

Never overwrite local uncommitted work merely because GitHub differs.

---

# 22. Final Product Identity

Auralis should become:

> **A private AI record studio trained around my music and my voice.**

Not merely a voice changer.

Not merely a mastering tool.

Not merely a generic song generator.

The differentiator is the combination:

```text
MY CATALOG
+
MY ARTIST DNA
+
MY TRAINED SINGING VOICE
+
LOCAL GENERATION
+
AURALIS MIX / MASTER
```

That is the path from the current repository to the desired product.
