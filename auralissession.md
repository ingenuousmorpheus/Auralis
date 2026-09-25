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

---

# 23. Session Log

Entries are appended oldest-first. Each entry uses: Goal, Starting State, Changed, Verification, Result, Findings, Gate/Blocker, Do Not Redo, Next Action.

## Session 001 — 2026-09-23 — AU-00 Audit + Baseline

### Goal
Establish a trustworthy baseline of what Auralis actually implements, verify it by running tests and the live app, and map it in `docs/AURALIS_CURRENT_ARCHITECTURE.md`. No feature work.

### Starting State
- Local `main` was at `87704d5`, one commit behind `origin/main`. `4910b1c` added this file.
- The working tree held uncommitted local work, an unrelated **Harmonic Reference** feature:
  - modified: `README.md`, `auralis/api/main.py`, `frontend/src/App.jsx`
  - untracked: `auralis/engine/harmony.py`, `docs/HARMONIC_REFERENCE.md`, `frontend/src/HarmonicReference.{jsx,css}`, `tests/test_harmony.py`
- The incoming commit touched only `auralissession.md`, so `git merge --ff-only origin/main` was safe. No reset, clean, stash or overwrite was used.
- **Starting HEAD after sync:** `4910b1c` (matches `origin/main`).

### Changed
- Added `docs/AURALIS_CURRENT_ARCHITECTURE.md`, the full architecture map, 19-item status table, API/frontend surface, persistence, tests, reuse map and gaps.
- Added this entry to `auralissession.md`.
- No source code changed. The local Harmonic Reference work was left exactly as found and is **not** part of the AU-00 commit.

### Verification
- **Backend tests:** `pytest -q --ignore=tests/test_harmony.py` → 28 passed (committed baseline). `pytest -q` including the local untracked harmony tests → 48 passed.
- **Frontend:**
  - `npm run build` passes.
  - `npm test` and `npm run lint` do not exist in `package.json`, so they were not run.
- **Live backend:** uvicorn on 127.0.0.1:8001.
  - `/health` → `0.8.0`.
  - The OpenAPI listing showed all routes documented in the architecture map.
- **Master:** synthetic stereo tone → `/upload` → `/master` (warm-soul) gave `internal-target`, −15.0 LUFS (the profile target), and `/download` returned 200.
  - A reference run with a distinct reference gave `mode: reference` at −14.0 LUFS.
  - A reference run that reused the target file was correctly rejected by Matchering.
- **Stem mix:** 3 synthetic stems → `/mix` (vocal-forward-rnb) gave −14.0 LUFS and −1.0 dBTP.
  - Roles vocal/drums/bass were detected at 0.98.
  - WAV, report and session downloads returned 200.
- **Voice APIs:**
  - `/voice/provider` → installed.
  - `/voice/profiles` → 1 profile, `studio-trained`, 1000 steps, 16.1 min / 137 clips, readiness 72, 1 paired calibration. No private paths in the response.
  - `/voice/finish` (rack upload plus instrumental), `/voice/pitch` (8 notes detected, 7 corrected) and `/voice/auto-polish` all returned 200 on every download, preview and report.
- **UI (browser pane):** home, master, stem, Voice Studio and Vocal Chain rack screens rendered with no console errors.
- **Seed-VC provider:** the provider venv has torch 2.4.0+cu121 with CUDA on an RTX 4070, and the trained `model/ft_model.pth` is present.
- **Live conversion FAILED for environmental reasons.** One 6 s synthetic test was run offline (`HF_HUB_OFFLINE=1`, nothing downloaded).
  - Running `inference.py` directly gave Windows `os error 1455` (paging file too small) while loading Whisper.
  - Host commit charge had 5.6 GB free of 63.7 GB, with LM Studio resident.
- All test audio was synthetic and generated in a scratch directory. No user audio was read, and nothing was uploaded.

### Result
**COMPLETE**, with one verification gated on the host environment: live Seed-VC conversion was not demonstrated this session. The code path, provider install, CUDA and trained checkpoint were verified. Profile `1fb8f19a27a9` shows the path has worked before: it was trained through it.

### Findings
- The implementation matches §1 of this file. The table below adds the caveats found in the code; the full evidence per item is in `docs/AURALIS_CURRENT_ARCHITECTURE.md`.

  | Area | Status |
  |---|---|
  | Mastering | IMPLEMENTED |
  | Stem mixing | IMPLEMENTED |
  | Reference matching | IMPLEMENTED |
  | Loudness/TP | IMPLEMENTED |
  | Voice profiles | IMPLEMENTED |
  | Dataset handling | IMPLEMENTED |
  | Training | IMPLEMENTED |
  | Pitch Polish | IMPLEMENTED |
  | Vocal Finish | IMPLEMENTED |
  | Instrumental-aware placement | IMPLEMENTED |
  | Launcher | IMPLEMENTED |
  | Style profiles | PARTIAL: `low_end_weight` is never read, and there are no bundled references |
  | Paired calibration | Ingest IMPLEMENTED. Pair-aware training DOCUMENTED-ONLY |
  | Persistence | PARTIAL: in-memory jobs, and `%TEMP%` job dirs that are never cleaned |
  | Diff-MST mixer | PLACEHOLDER |
  | Windows packaging | DOCUMENTED-ONLY |
  | Persistent song projects | NOT FOUND |

- §1 also omits `auralis/engine/console.py`, the DSP execution and summing layer that the mix path depends on. This is an addition, not a correction.
- Version drift and stale text:
  - Code and UI are `0.8.0`, which is consistent across `pyproject.toml`, `__init__.py`, `/health` and `package.json`.
  - The `6e28bbc` commit message says 0.5.
  - `RECONSTRUCTION_ROADMAP.md` says 0.3.
  - `DESIGN.md` is titled "LocalMaster".
  - The `api/main.py` docstring still says "Phase 1 — master-only".
- Port drift: `auralis/run.py` and `DESIGN.md` use 8000. The launcher, README and frontend use 8001.
- Provider error surfacing: through `SeedVCProvider.convert` the host-memory failure appeared as "Unknown Seed-VC error" with empty output. The direct run showed the real traceback.
- Out-of-repo experiment: the live profile and provider contain `*_paired_20260625_*` model and holdout artifacts. No code on `main` produces them.
- Naming collision to resolve before AU-09: the local uncommitted `auralis/engine/harmony.py` is note-domain reference *analysis*. §10 plans `auralis/voice/harmony.py` for harmony/doubles *generation*.
- The memory contention in §16 (GPU Strategy) already shows up in practice: a resident local LLM (LM Studio) alongside Seed-VC exhausted commit memory. This supports building the scheduler before stacking more heavy models.

### Gate/Blocker
- Live Seed-VC conversion needs more free commit memory: close LM Studio or other large processes, or enlarge the page file. After that, re-run one conversion through `POST /voice/convert` to close the last verification.
- AU-00 was otherwise not blocked.

### Do Not Redo
- The DSP engine, voice pipeline and API surface are mapped in `docs/AURALIS_CURRENT_ARCHITECTURE.md`. Update that document instead of re-auditing from scratch.
- Seed-VC is installed with CUDA working, and the profile is already trained. Do not reinstall or retrain to "verify".
- Matchering rejecting a reference identical to the target is expected behavior, not a bug.

### Next Action
Begin **AU-01 Persistent Projects**:
- Add `auralis/projects/store.py`, a `ProjectStore` modeled on `VoiceProfileStore`:
  - root `%LOCALAPPDATA%\Auralis\projects\<12-hex id>\`
  - id regex validation
  - `project.json` + `sources/ stems/ vocals/ mixes/ masters/ reports/`
- Add API routes to create, list, open and close projects.
- Add a way to register an existing job's outputs (`output_path`, `master_path`, `session_path`) into a project, so the current master, mix and voice workflows save into projects unchanged.
- Gate test: create, restart the backend, reopen, and confirm all assets are still linked.

Optional before or alongside AU-01, no rewrites:
- Clear the environment blocker and re-verify `/voice/convert`.
- Fix the `run.py` port (8000 → 8001).

## Session 002 — 2026-09-23 — AU-01 Persistent Projects

### Goal
Build the project/session model so that a song's sources and generated assets live in a reopenable project that survives backend restarts (§14). Make the existing workflows save into projects **without changing how they run**.

### Starting State
- `main` at `01cfb8d` (AU-00 done).
- One AU-00 check was still open: live Seed-VC conversion. At the start of this session commit charge had 6.7 GB free of 63.7 GB, with LM Studio still resident, so the check could not be re-run.
- The local uncommitted Harmonic Reference work was still in the tree. It shares `auralis/api/main.py`, `frontend/src/App.jsx` and `README.md` with this session's work, so only this session's hunks were staged for commit (see Changed).

### Changed
- **New backend package `auralis/projects/`:**
  - `store.py`: `ProjectStore` / `Project` / `ProjectAsset`. Modeled on `VoiceProfileStore`: 12-hex ids, root at `%LOCALAPPDATA%\Auralis\projects\`, kind folders, atomic `project.json`, append-only history, open/closed state (closed means read-only), copy-in assets with size and SHA-256, and `verify(deep=)`.
  - `jobs.py`: `job_kind` and `job_outputs` map every existing job kind onto assets with provenance. Mastering reference tracks are never imported, which preserves the rule that references live only in the job temp folder.
- **New `auralis/api/projects.py`:** a FastAPI router for `/projects` (CRUD, open, close, verify, import-job, asset upload/download/delete).
- **`auralis/api/main.py`:** two added lines (router import and `app.include_router`).
- **Frontend:**
  - New: `ProjectsPanel.jsx` ("My Projects" mode), `SaveToProject.jsx` (reusable save control), `Projects.css`.
  - `App.jsx`: added the Projects home card and mode, and Save-to-project on the master/mix result.
  - `VoiceStudio.jsx`: Save-to-project on the converted, pitch-polished and studio-polished results.
  - `VocalRack.jsx`: Save-to-project on the rack result.
- **Tests and docs:**
  - New `tests/test_projects.py` (14 tests).
  - `docs/AURALIS_CURRENT_ARCHITECTURE.md` updated: item 15, directories, API, frontend, new "Project model" section, tests, gaps.

### Verification
- `pytest -q` including the local harmony tests → 62 passed. Excluding the local untracked harmony tests → 42 passed (28 baseline + 14 new). No baseline test regressed.
- `npm run build` passes.
- **Real-process gate run.** uvicorn ran with `LOCALAPPDATA` pointed at a scratch folder so no test data touched the real project store.
  1. A real 3-stem `/mix` job and a `/voice/finish` job (with instrumental) were imported into project "Gate Test Song". A direct audio upload was added too, for 12 assets in total.
  2. The project was closed.
  3. The backend **process was killed and restarted**.
  4. The project was listed as `closed · 12`.
  5. `POST /open` reported `integrity.linked = true`, and `verify?deep=true` also gave `linked: true`.
  6. The master downloaded from the project was **byte-identical** (`cmp`) to the master downloaded from the job before the restart.
- **UI (browser pane):**
  - The Projects screen listed the project and showed all 12 assets grouped by kind, with players and provenance.
  - Close hid "Add audio files". Reopen restored it.
  - In the Vocal Chain rack, a generated test WAV → Analyze + Render → **Save** gave "✓ Saved 3 files to “Gate Test Song”".
  - No console errors.
- All test audio was synthetic. No user audio or voice data was read, and nothing left the machine.

### Result
**COMPLETE.** AU-01 gate: *"A project can be created, closed, reopened, and all source/generated assets remain linked."* This passed across a real backend restart and in the automated API test `test_api_master_job_saved_to_project_survives_restart`.

### Findings
- Files are **copied** into projects, never moved or linked. The job temp folder is never cleaned (AU-00 finding 3), but projects must not depend on it, and copying makes that safe.
- A rack-uploaded vocal is saved as `rack_source.wav`, because vocal-finish jobs do not keep the original upload name. This is cosmetic.
- Work currently flows **job → project** only. Nothing starts a job *from* a project asset yet. AU-10 assembly will need that direction (e.g. a `/mix` that takes project stem ids).
- `Project.voice_profile_id` exists and can be set via `PATCH` but is not yet shown in the UI. It is the hook for AU-08.

### Gate/Blocker
- AU-01: none.
- Still open from AU-00: the live Seed-VC conversion check, which needs free commit memory (close LM Studio or enlarge the page file).

### Do Not Redo
- The project storage layout, manifest schema v1, and the job → asset mapping are settled.
- Extend `auralis/projects/` rather than adding a second persistence layer.
- Mastering references are intentionally excluded from projects. Do not "fix" this.

### Next Action
Begin **AU-02 My Music Library**:
- Catalog import and analysis of user-owned songs under `%LOCALAPPDATA%\Auralis\artist\library\`, reusing the extractors listed in the architecture Reuse Map: `engine/analysis.analyse`, `engine/loudness.measure`, `voice/pitch.detect_key`.
- New analysis is needed for tempo, section structure and energy curve.
- Gate: 10 user-owned songs give useful BPM/key/structure/harmony/energy metadata.
- **This needs the user's own songs.** Ask which folder to import from; never pick files on your own.

## Session 003 — 2026-09-24 — AU-02 My Music Library

### Goal
Import the user's own catalog, analyse every song locally, and produce useful BPM/key/structure/harmony/energy metadata (§3, AU-02 gate). The catalog came from two user-named folders. No Artist DNA aggregation yet (that is AU-03).

### Starting State
- `main` at `23675b7` (AU-01 done).
- Seed-VC live check still blocked by host commit memory.
- The user's local Harmonic Reference work was still uncommitted in the tree, so only this session's hunks of `auralis/api/main.py` and `frontend/src/App.jsx` are staged.
- The catalog is on a network drive (~4 MB/s reads): 16 stem `.zip` packages, KITS-style stem folders with demos and lyrics `.txt`, and loose mixes/instrumentals/remixes. ~5.7 GB total.

### Changed
- **New package `auralis/artist/`:**
  - `library.py`
    - in-place scanning and grouping: zip → stem set; folder with 2+ named stems → stem set plus `reference` files; else one song per file
    - lyrics linking by path
    - stem-role naming, KITS `_backing_` = instrumental, variant tags
    - `LibraryStore` (`%LOCALAPPDATA%\Auralis\artist\`) with fingerprints, stale detection and the include-for-DNA toggle
    - `SongAudio` loads zip members one at a time via temp files and sums stems as it reads
  - `analyze.py` (`ANALYSIS_VERSION = 3`): global loudness/LRA/width, tempo, bars, key, energy, chords/roman numerals/progressions, structure, rhythm, lead-vocal melody, production balance. Details in `docs/AURALIS_CURRENT_ARCHITECTURE.md` → "My Music library".
  - `__main__.py`: CLI `python -m auralis.artist add|scan|analyse|list`.
- **New `auralis/api/artist.py`:** `/artist/library` router (folders, rescan, songs, include toggle, background analysis job).
- **`auralis/api/main.py`:** router include (2 lines).
- **Frontend:** new `MyMusic.jsx` + `MyMusic.css` ("My Music" mode). `App.jsx` gets the home card and mode.
- **Tests and docs:** new `tests/test_artist_library.py` (24). Architecture doc updated.

### Verification
- `pytest -q` including the local harmony tests → 86 passed. Excluding them → 66 passed (42 previous + 24 new). `npm run build` passes.
- **Ground truth test:** a synthetic song (90 BPM, C major, I–V–vi–IV, V-C-V-C with backing vocals only in choruses) gave:
  - tempo within ±1 BPM, key C major, the progression
  - chorus found via backing-vocal activity
  - melody range from the lead stem
  - a mix-only repeat found
  - a silent "Lead Vocals" stem ignored
- **Real catalog:** 2 folders → 74 songs (33 stem sets: 16 zips + 17 folders; 41 mixes); 3 lone stems skipped. `analyse` v3: **74/74 done, 0 failed**, ~25–120 s per song. A snapshot test proves analysis never writes to catalog folders.
- **Consistency on the user's own versions of the same song** (the only ground truth available without asking the user):
  - Tempo agreed within 0.3 BPM for 4 of 5 vocal/instrumental or remix pairs.
  - One 3:2 error (a vocal version vs its instrumental).
  - Keys agreed on key family (relative major/minor, or a fifth apart) but not always on the exact tonic.
- **UI (browser pane, real library):** 74/74 analysed. The song table and detail view render (energy/section timeline, progressions, rhythm, vocal range, stem balance). No console errors. No horizontal overflow at 1024 or 375 px.

### Result
**COMPLETE** against the gate: well over 10 user-owned songs imported, and every one has BPM, key, structure, harmony and energy metadata. The limits below are documented rather than hidden. The user has not yet spot-checked values against songs they know.

### Findings
- **Superseded within this session: analysis v1 and v2.**
  - v1 labelled sections by chord repetition. It fragmented R&B songs that loop one 4-bar cycle (17 all-different sections in one song). Laplacian segmentation was tried and was worse (1–2-bar label flipping). It was replaced by **arrangement-based** segmentation from per-bar stem activity. In stem sets, choruses show up as backing vocals entering.
  - v2 used arrangement for mix-only songs too. Loud masters have flat arrangement energy, so those came out as "S S". Mix-only songs now use **aligned bar-by-bar repetition** of chroma + timbre.
  - v1/v2 tempo was **quantised** to librosa's frame grid (~5 BPM steps at 120; 11 songs read exactly 123.0). v3 fits a line through the beat times: on synthetic clicks, 93.0 → 93.0 and 120.0 → 120.0 (the grid gave 92.3 and 117.5).
  - v1/v2 treated near-silent stems as active and extracted junk "melodies" from separation bleed. Several type-beat packages ship a "Lead Vocals" stem 18–97 dB below the music. v3 ignores stems >30 dB below the loudest, and reports no melody under 5% voiced frames.
- `global.vocal_melody_found` replaced a first-draft `instrumental_detected` flag. Stem folders whose vocal lives only in the demo MP3 are *not* instrumentals. The 74 saved analyses were migrated in place (derived from the saved `melody` field; no audio re-read).
- Tempo half/double (and one 3:2) ambiguity is inherent. BPM is folded into 65–145 and alternates are stored. Some slow jams likely read at double time.
- Key detection is reliable for the **key family** but not the exact tonic/mode (confidence ~0.4). **AU-03 should aggregate keys by pitch-class set / key signature**, not by exact key name.
- Mix-only structure is noticeably weaker than stem-set structure. AU-03 should weight stem sets higher for form, melody and rhythm traits.
- Host memory is the practical constraint. Two analysis processes plus a resident local LLM exhausted commit memory (two "Unable to allocate" failures, both succeeded on retry). The stem loader was changed to sum stems as it reads.
- Catalog metadata (song titles, paths) lives only in `%LOCALAPPDATA%` and is deliberately **not** written into this repo.

### Gate/Blocker
- AU-02: none.
- Still open from AU-00: live Seed-VC conversion (host commit memory).

### Do Not Redo
- The catalog is indexed and analysed at v3. `python -m auralis.artist analyse` only re-runs pending/stale/older-version songs.
- Laplacian segmentation and chord-repetition labelling were tried and rejected for this catalog (see Findings).
- Do not re-add `instrumental_detected`. Use `vocal_melody_found`.

### Next Action
Begin **AU-03 Artist DNA V1**:
- Aggregate `artist/analyses/*.json` over `included` songs into an inspectable profile. Weight stem sets higher, use key families, report tempo with its octave ambiguity, and describe typical form, chord vocabulary and progressions, groove, vocal range and production balance.
- Show it in the UI with the evidence behind each trait.
- **Before that, ask the user to** spot-check 3–5 songs they know (BPM/key), and to untick songs that should not shape their DNA (covers, type beats, other artists' remixes).

## Session 004 — 2026-09-24 — Console UI redesign (not a roadmap phase)

### Goal
Replace the old home-card interface with the Suno-style layout the user asked for: sidebar, Create panel beside a song list, and a persistent player. Restyle it as an elegant metallic-gold "starship bridge in a cyberpunk city" console, with a 3D morphing logo and light-sweep headings. It was designed first in Claude Design (private canvas "Auralis Studio Redesign") and approved by the user, then built into the real app.

### Starting State
- `main` at `3708acb` (AU-02).
- The user's uncommitted Harmonic Reference work was still in the tree.
- During this session the Claude session crashed and the user restarted it. The user then reported "Auralis never opened".

### Changed
- **New frontend files:**
  - `theme.css`: tokens, effects, shell; remaps the old App.css tokens to gold
  - `ui.jsx`: icons, covers, `catalogStats`
  - `Shell.jsx`: `Sidebar` with morphing logo and voice card; `PlayerBar`
  - `CreatePage.jsx`, `MasterMix.jsx`, `StudioPage.jsx`
- **Rewritten:**
  - `App.jsx`: the shell and page routing. Harmonic Reference loads through `import.meta.glob` only when its file exists.
  - `MyMusic.jsx` and `MyMusic.css`: design layout, "Your sound so far" from real aggregates, play button.
- **Small edits:**
  - `VoiceStudio.jsx`: the back button is optional, and a "Checking the local engine…" state fixes the AU-00 loading flash.
  - `index.html`: background colour.
- **Backend:**
  - `LibraryStore.preview_path` + `GET /artist/library/songs/{id}/preview`, so the player can play the catalog.
  - `LibraryStore._forget` deletes previews along with analyses.
- **Tests:** 2 new tests in `tests/test_artist_library.py`.

### Verification
- `pytest -q` including the local harmony tests → 88 passed. Excluding them → 68 passed. `npm run build` passes.
- **Real launcher:** `tools/stop_auralis.ps1` stopped the instance the user had started at 15:48. It was still running and serving live-reloaded work-in-progress files, which is the likely cause of "never opened". `tools/start_auralis.ps1` then printed "Auralis is ready" (exit 0) and opened the browser.
- **Preview endpoint on real data:** a full mix gives 200 `audio/wav` in 6.7 s (network drive). A zipped stem set renders in 10.1 s on first play and serves from cache in 0.03 s.
- **Browser pane, real library:**
  - All 9 screens render with no runtime errors: Create, My Music, Studio, My Voice, Projects, Master, Mix, Vocal chain, Harmonic reference.
  - A catalog song played through the player (position advancing).
  - My Voice shows the installed engine and the trained profile once loaded.

### Result
**COMPLETE.** The redesigned UI is live on the existing backend. Song generation behind the Create button is honestly labelled as the next phase.

### Findings
- The launcher treats an already-running instance as success ("already running", then it opens the browser). If that instance serves half-written files mid-edit, the user sees a broken or blank page. Restart it with Stop/Run after large frontend changes.
- `import.meta.glob` lets the committed shell show the user's uncommitted Harmonic Reference locally without making the GitHub build depend on it.
- Suno's layout was the reference; no Suno or Star Trek names, logos or assets are used. The "LCARS" look was deliberately not copied: only the mood (gold on black, console brackets, scanlines) was.

### Gate/Blocker
- None for the UI.
- Still open: live Seed-VC check (host commit memory). The user's spot-check and DNA include/exclude choices come before AU-03.

### Do Not Redo
- The shell, theme tokens and page map are settled. New features add a page or a card, not a new shell.

### Next Action
AU-03 Artist DNA V1, once the user has spot-checked a few songs and set the DNA toggles in My Music.


---

# Research Addendum — R&B Theory Atlas / Era-Aware Composition Intelligence

**Added:** 2026-09-24  
**Purpose:** Give Auralis a research-backed R&B music-theory layer that can sit beside Artist DNA and guide original composition by era, harmony, groove, form and vocal phrasing.

## Core idea

Auralis should not rely only on `Artist DNA` or a black-box music model.

The stronger architecture is:

```text
R&B THEORY ATLAS
        +
ARTIST DNA
        +
CURRENT SONG BRIEF
        +
USER VOICE RANGE
        ↓
SONG BLUEPRINT
        ↓
ORIGINAL COMPOSITION
```

The Atlas is not a “hit generator” and should never promise commercial success. Its job is to make generation more stylistically informed by historically common and musically effective R&B practices while preserving originality.

Use the terms:

- **era fit**
- **style fit**
- **harmonic familiarity**
- **vocal fit**
- **hook/contrast**
- **originality**

Do not expose a “probability of becoming a hit.”

## Research findings to encode

### 1. Popular-music harmony is better modeled as reusable schemata than isolated chord names

Corpus work using the McGill Billboard corpus treats recurring harmonic patterns as probabilistic templates / schemata rather than rigid rules. This supports the Atlas design: store recurring relationships, transitions, cadence behavior and harmonic rhythm rather than “magic chords.”

A 2026 Music Theory Online study of “soul dominants” used the McGill Billboard corpus and identified **2,033 eleventh-quality chords across 153 songs**. The study found that their behavior depends on context, including incoming bass motion and metrical placement. This is useful for generation because Auralis should model **what tends to happen before and after a sonority**, not just the sonority itself.

Research source:
https://mtosmt.org/issues/mto.26.32.2/mto.26.32.2.fink.html

### 2. The “soul dominant” should be an explicit R&B harmonic feature

The dominant-eleventh / suspended-dominant family is historically important enough in soul/R&B to deserve a first-class Atlas feature.

Store abstract labels such as:

```text
V11
V9sus
IV/V
sus-dominant color
bass-pedal dominant color
```

For each occurrence/profile store:

- era
- tonal context
- scale-degree bass
- approach interval
- exit interval
- strong/weak metrical position
- resolution tendency
- section role
- tension level

Do not assume every V11 must resolve like a classical V7.

### 3. Quiet Storm / slow R&B often benefits from harmonic stasis and pedal-based color

Music Theory Online’s analysis of Smokey Robinson’s “Quiet Storm” describes an extended pedal-based texture: a sustained/pedal foundation, Amaj9 in the intro/verse, and a chorus shifting between Amaj7 and Dmaj7 while retaining the pedal. The important reusable lesson is **not the song’s exact progression**; it is that slow R&B can create motion through:

- sustained pedal tones
- extended major harmony
- layer accumulation
- timbral change
- register change
- section density

without frequent chord changes.

Research source:
https://www.mtosmt.org/issues/mto.25.31.4/mto.25.31.4.hudson_wang.html

This should inform an **80s R&B / Quiet Storm** era preset, while acknowledging that the Quiet Storm style begins earlier and develops into the 1980s radio/R&B sound.

### 4. Neo-soul harmony should use extensions, borrowing and smooth voice-leading

Useful neo-soul features supported by contemporary pedagogy include:

- maj7 / min7
- maj9 / min9
- 11ths
- 13ths
- altered dominants
- secondary dominants
- borrowed chords / modal interchange
- passing chords
- rootless or fifth-less voicings
- close voice-leading between chord colors

Research sources:
https://www.pickupmusic.com/blog/neo-soul-guitar-chords-for-beginners
https://www.pickupmusic.com/blog/10-essential-neo-soul-chord-progressions-for-guitarists
https://online.berklee.edu/courses/harmony-2
https://college.berklee.edu/courses/hr-216

Berklee’s harmony curriculum reinforces that modal interchange, secondary/extended dominants, deceptive resolution, guide tones, melodic rhythm, harmonic rhythm and melody/harmony relationships are appropriate building blocks for contemporary harmony.

### 5. Groove timing is part of the composition, not an afterthought

Oxford research on neo-soul groove describes deliberate microtiming offsets among rhythmic layers. In one analyzed D’Angelo groove, pulse-carrying layers differ by roughly **50–80 ms**, and the broader literature describes offsets reaching about **50–100 ms** in neo-soul contexts.

The Atlas should therefore store groove descriptors such as:

- kick offset
- snare offset
- bass offset
- comping offset
- swing ratio
- push/pull tendency
- quantization strength
- pocket width

Do not hard-code one delay amount. Treat microtiming as a style distribution and allow section-dependent variation.

Research sources:
https://academic.oup.com/book/56186/chapter/443057660
https://academic.oup.com/mts/article/45/2/181/7234305

### 6. R&B vocal phrasing should be modeled relative to the beat and backbeat

Oxford’s `Swinglines` research specifically examines American R&B singers in relation to accompaniment, beat and snare backbeat. The reusable idea is that lead vocals should not be represented only as a sequence of MIDI notes.

For each vocal phrase store abstract features:

- scale-degree start
- scale-degree end
- highest/lowest scale degree
- interval-size distribution
- stepwise vs leap percentage
- contour: rising / falling / arch / wave / static
- phrase length in beats/bars
- pickup length
- onset offset from beat
- relationship to snare/backbeat
- syncopation density
- repeated-motif count
- melisma density
- average notes per syllable
- held-note tendency
- phrase-ending run tendency
- register lift by section
- call/response behavior
- ad-lib density
- breath spacing

Research source:
https://academic.oup.com/book/57410/chapter-abstract/464767463

Auralis should learn **phrasing behavior**, not copy a third-party singer’s exact melody.

### 7. Form and section lift belong in the Atlas

Popular-music theory research shows that verse/prechorus/chorus arrival can be driven by harmony, texture, register, repetition or a combination. For R&B generation, section contrast should therefore be modeled as a multi-variable “lift,” not just “make the chorus louder.”

Store:

- harmonic tension change
- chord-rhythm change
- bass-register change
- vocal-register change
- background-vocal entry
- drum-density change
- stereo-width change
- textural saturation
- hook repetition
- melody repetition/variation

Research source:
https://www.mtosmt.org/issues/mto.22.28.3/mto.22.28.3.nobile.html

### 8. Loop-based harmony and tonal ambiguity are valid modern choices

Broader post-1990 pop research documents axis progressions, loop-based harmony, hybrid tonics and tonal ambiguity. These should be available to modern/crossover R&B presets, but they must not be treated as uniquely R&B features.

Research sources:
https://mtosmt.org/issues/mto.17.23.3/mto.17.23.3.richards.html
https://www.mtosmt.org/issues/mto.19.25.4/mto.19.25.4.duinker.html

## Key-selection rule

Do **not** build a simplistic “most hit songs are in key X” rule.

A progression should first be represented in Roman numerals / scale degrees, then mapped into a key using:

1. requested era/mood
2. user’s trained/comfortable vocal range
3. desired chorus high point
4. tessitura of verses
5. instrument/register constraints
6. Artist DNA key-family tendencies

This is more useful than copying the original key of a successful song.

The Atlas may store key/mode distributions for research, but generation should prioritize **voice fit** and transposability.

## Era profiles

Create configurable profiles rather than hard rules.

### 70s Soul / R&B

Candidate traits to measure and validate:

- dominant 7/9/11 colors
- “soul dominant” / sus-dominant behavior
- gospel/blues borrowing
- vamps and pedal tones
- bass-driven harmonic motion
- call-and-response
- funk-derived harmonic stasis
- live-feel groove

### 80s R&B / Quiet Storm

Candidate traits to measure and validate:

- maj7 / maj9 / min7 / min9 colors
- slower harmonic rhythm
- pedal-based harmony
- electric-piano / synth-pad harmonic beds
- smooth inner-voice motion
- spacious verses
- stronger register/texture lift into chorus
- restrained verse phrasing with higher-intensity chorus/ad-libs

### 90s R&B

Candidate traits to measure and validate:

- loop progressions and R&B-line behavior
- richer prechorus-to-chorus lift
- gospel-derived harmony where appropriate
- layered background vocals
- stronger vocal-run/ad-lib vocabulary
- verse/chorus register contrast
- drum groove increasingly influenced by hip-hop

### Neo-Soul

Candidate traits:

- 7/9/11/13 harmony
- altered/secondary dominants
- modal interchange
- borrowed chords
- passing chords
- rootless/compact voicings
- strong voice-leading
- intentional microtiming / laid-back pocket
- melody woven around rather than strictly on the grid

### 2000s / Contemporary R&B

Candidate traits to measure and validate:

- reduced harmonic rhythm / loop-based harmony
- minor/modal palettes
- stronger production-driven section contrast
- hybrid-tonic / ambiguous-center possibilities
- sparse verse / expanded chorus
- vocal rhythm as a major hook carrier
- optional pop crossover axis-type loops

### Modern Alternative R&B

Candidate traits to measure and validate:

- harmonic minimalism when appropriate
- modal ambiguity
- texture/atmosphere as structural material
- sub-bass-centered arrangement
- conversational or highly syncopated lead phrasing
- contrast created by timbre, register and negative space
- selective use of rich extended chords rather than constant density

These era profiles are **starting hypotheses**. Auralis should refine them from curated research and approved datasets, not freeze them as stereotypes.

## Human-readable “R&B Cheat Sheet”

The user requested an Excel-style cheat sheet.

Plan a human-readable workbook:

`docs/research/RNB_THEORY_ATLAS.xlsx`

Recommended sheets:

1. **Era Profiles**
   - era
   - subgenre
   - BPM tendency
   - harmonic rhythm
   - chord colors
   - groove feel
   - vocal behavior
   - structure tendencies
   - production notes

2. **Progression Families**
   - id
   - Roman numeral pattern
   - mode
   - cadence/loop type
   - tension profile
   - era affinity
   - section affinity
   - reharmonization options

3. **Chord Vocabulary**
   - chord quality
   - function
   - common approach
   - common exit
   - extensions
   - omissions
   - inversion/rootless behavior
   - era affinity

4. **Vocal Phrase Patterns**
   - section
   - scale-degree start/end
   - contour
   - phrase bars
   - pickup behavior
   - syncopation
   - melisma density
   - register
   - hook repetition

5. **Groove / Pocket**
   - era
   - BPM band
   - swing feel
   - kick/snare/bass relationship
   - microtiming profile
   - quantization range

6. **Song Evidence**
   - song
   - artist
   - year
   - chart/source dataset
   - abstract harmonic/form/vocal observations
   - source citation
   - confidence

7. **Sources**
   - title
   - author
   - publisher
   - URL/DOI
   - year
   - notes

### Source-of-truth rule for the workbook

Do not make the binary XLSX the only runtime database.

Preferred flow:

```text
research / approved rows
        ↓
RNB_THEORY_ATLAS.xlsx   ← human review/editing
        ↓
CSV/JSON export
        ↓
auralis/theory/rnb_atlas.json
        ↓
Auralis Composer
```

Or, if implementation simplicity is better, keep JSON as canonical and regenerate XLSX for human review. Pick one canonical representation and document it; do not maintain two unsynchronized truth sources.

## Runtime architecture

Add later:

```text
auralis/theory/
    schema.py
    atlas.py
    era_profiles.py
    retrieval.py
    scoring.py
    copyright_guard.py
```

Blueprint request example:

```json
{
  "genre": "rnb",
  "era": "80s_quiet_storm",
  "harmony_color": "romantic_extended",
  "groove": "laid_back",
  "vocal_style": "smooth_with_chorus_runs",
  "artist_dna_weight": 0.65,
  "theory_atlas_weight": 0.35
}
```

The composer should retrieve **multiple compatible options**, not one deterministic “correct” progression.

Example internal response:

```text
ERA: 80s R&B / Quiet Storm

Harmony candidates:
A. pedal + maj9 color
B. slow ii–V-derived extended cycle
C. IV/ii-centered borrowed-color loop

Voice fit:
transpose candidate B down 2 semitones
because target chorus peak exceeds comfortable range

Artist DNA:
prefers minor key family and 82–94 BPM

Final blueprint:
original hybrid selected from theory + Artist DNA
```

## Scoring

Score candidates across separate dimensions:

```text
era_fit
artist_fit
voice_fit
harmonic_coherence
section_contrast
hook_support
novelty
similarity_risk
```

Do not collapse this into a fake “hit probability.”

## Copyright / originality boundary

Do not assume that “chords are never copyrighted.”

The U.S. Copyright Office describes musical works as potentially including **melody, rhythm and/or harmony**. Therefore Auralis should take the conservative engineering approach:

### Third-party research songs

Store:

- Roman-numeral abstractions
- chord-quality statistics
- transition counts
- key/mode
- tempo bands
- form
- aggregate scale-degree tendencies
- contour classes
- rhythmic/microtiming descriptors
- melisma density
- section-level characteristics
- citation/provenance

Do **not** store as reusable generation templates:

- complete note-for-note lead melodies
- long exact MIDI transcriptions
- lyric text
- raw audio
- identifiable full melodic hooks
- exact arrangement reconstruction

### User-owned catalog

Auralis may analyze the user’s own authorized material at full detail locally, but the existing originality/similarity guard still applies so new output does not merely duplicate an earlier song.

U.S. Copyright Office references:
https://www.copyright.gov/help/faq/faq-gram.html
https://www.copyright.gov/comp3/2017version/docs/compendium.pdf

This is an engineering risk-reduction rule, not legal advice.

## Build-order change

Do **not** wait until the end of the roadmap to add this intelligence.

Revised sequence around composition:

```text
AU-03   Artist DNA V1
        ↓
AU-03B  R&B Theory Atlas Data Foundation
        ↓
AU-04   Song Blueprint Generator
        ↓
AU-05   MIDI / Structured Composer
```

### AU-03B — R&B Theory Atlas Data Foundation

Implement only the research/data layer:

- schema
- era profiles
- curated research rows
- source/provenance records
- progression families
- chord vocabulary
- vocal-pattern abstractions
- groove/microtiming profiles
- JSON/CSV runtime representation
- optional XLSX human-review export

No audio generation yet.

**Gate:**

> Given an era selector such as “80s R&B,” Auralis can return several documented, transposable harmony/groove/vocal-profile candidates with source provenance, without reproducing a copyrighted melody.

### AU-04 integration

Song Blueprint should combine:

```text
prompt
+
Artist DNA
+
R&B Theory Atlas
+
voice range
+
originality constraints
```

and explain why a candidate was chosen.

### AU-05 integration

The structured composer should use:

- Roman numeral progression
- selected key/transposition
- voicing rules
- voice-leading targets
- groove timing profile
- section lift
- vocal phrase constraints

instead of blindly copying song examples.

## UI addition

Create should eventually expose:

```text
ERA
70s Soul
80s R&B / Quiet Storm
90s R&B
Neo-Soul
2000s R&B
Modern R&B

HARMONY
Familiar
Rich
Gospel-influenced
Dark
Romantic
Experimental

VOCAL APPROACH
Smooth
Conversational
Melismatic
Falsetto-heavy
Power ballad
Ad-lib heavy

GROOVE
Straight
Laid-back
Deep pocket
Swing
Hip-hop influenced
```

Keep advanced controls collapsible. Default Create remains simple.

## Research principle going forward

For third-party songs, Auralis should learn **relationships and distributions**, not memorize songs.

For the user’s own songs, Auralis can use deeper local analysis.

Target philosophy:

```text
UNDERSTAND WHY THE STYLE WORKS
+
UNDERSTAND HOW I WRITE
+
WRITE SOMETHING NEW FOR MY VOICE
```

---

## Session 005 — 2026-09-24 — R&B Theory Atlas research added

### Goal
Research a copyright-conscious theory layer for R&B generation and add it to the roadmap before AU-04/AU-05 composition work.

### Result
**DOCUMENTED / RESEARCH COMPLETE FOR V1 DESIGN.**

The session now includes:
- corpus-backed soul-dominant concept
- Quiet Storm pedal/harmonic-stasis model
- neo-soul extensions/borrowing/voice-leading
- groove microtiming
- R&B vocal phrase descriptors
- section-lift/form descriptors
- era-profile schema
- XLSX cheat-sheet plan
- JSON runtime plan
- copyright/originality boundary
- new AU-03B phase inserted between Artist DNA and Song Blueprint

### Next Action
Continue the existing next step first: finish the user’s My Music spot-check/include-exclude cleanup, then AU-03 Artist DNA V1. After AU-03 passes, build AU-03B before AU-04.


## Session 006 — 2026-09-24 — AU-03 Artist DNA V1 + AU-03B R&B Theory Atlas

### Goal
The user said to start both, so I built AU-03 (Artist DNA V1) and then AU-03B (R&B Theory Atlas data foundation), in the order Session 005's build order sets. No audio generation.

### Starting State
- `main` at `e17cb28`: the merge of the user's Session 005 research addendum with the play-from-cover fix.
- Session 005 asked for the My Music spot-check and include/exclude cleanup before AU-03. That was not done yet, so **DNA is computed live on every request** and follows the user's toggles whenever they make them. Nothing needs redoing afterwards.
- The user's uncommitted Harmonic Reference work was still in the tree.

### Changed
- **AU-03:**
  - `auralis/artist/dna.py`: `build_dna`, `family_key`, `_families`, `canonical_loop`.
  - `GET /artist/dna` on the artist router. The router prefix is now `/artist`, and the library routes spell out `/library`; URLs are unchanged.
  - `frontend/src/DnaPage.jsx`, plus an "Artist DNA" sidebar item and helix icon.
- **AU-03B:**
  - `auralis/theory/`: `schema.py` (validation and copyright guard), `atlas.py` (candidates, `suggest_keys`), `data/rnb_atlas.json` (canonical).
  - `auralis/api/theory.py`: `/theory/eras`, `/theory/sources`, `/theory/candidates`, included in `main.py` (2 lines).
  - `tools/export_atlas.py` produces `docs/research/RNB_THEORY_ATLAS.xlsx`.
  - `frontend/src/AtlasPanel.jsx`: the "Era & style" panel in Create's Advanced mode.
- **Other:**
  - `pyproject.toml`: `research` extra (openpyxl, installed locally for the export) and package data for the Atlas JSON and profile YAMLs.
  - Tests: `tests/test_artist_dna.py` (13), `tests/test_theory_atlas.py` (22).

### Verification
- `pytest -q` including the local harmony tests → 123 passed. Excluding them → 103 passed. `npm run build` passes.
- **DNA on the real library**: 74 songs, 51 song families, 33 stem sets.

  | Trait | Result |
  |---|---|
  | Tempo | 83–120 BPM, centred on 94 |
  | Key | 62% minor, spread across keys (top family only 15%) |
  | Harmony | ~1.4 chord changes per bar, 92% diatonic |
  | Form | first chorus ~0:37, intros ~8 bars |
  | Groove | syncopated (49% off the beat), straight |
  | Melody | written F♯3–B♭4, against a trained voice of D3–C5 |

- **DNA page (browser pane, real data):** every trait card renders.
- **Atlas gate:** "80s R&B / Quiet Storm" with the user's voice range and DNA families gives:
  - three `sourced` harmony candidates (pedal maj9 stasis, maj7 sway a fourth apart, soul-dominant arrival), each keyed to A♭ major because it "fits your range with 1 semitone to spare; a key family you use often"
  - vocal and groove profiles, each with sources and status
  - no melody fields anywhere in the answer
- **Era & style panel (browser pane):** shows the same results.
- **Workbook:** 7 sheets written (6 eras, 12 progressions, 12 chord colours, 6 vocal patterns, 6 grooves, 2 evidence rows, 12 sources).

### Result
**AU-03 COMPLETE** against its gate: the UI describes recurring traits across the user's music without generating anything.

**AU-03B COMPLETE** against its gate: given "80s R&B", Auralis returns several documented, transposable harmony, groove and vocal candidates with provenance, without reproducing a copyrighted melody.

Both have the caveats below.

### Findings
- **First-draft DNA problems, fixed before commit.**
  - Loop rotations were counted as different loops ("i–v–i–v" and "v–i–v–i"); `canonical_loop` merges them.
  - "Common forms" was dominated by trivial "S" forms from weak mix-only structure. Only chorus-bearing forms of 4+ sections count now.
  - The key headline named a "most often" family holding only 15%. It now says the keys are spread out.
  - Tempo bands were sorted as text ("100s" before "60s").
- **First-draft key-fit rule was wrong.** It assumed a 23-semitone lead span, which is wider than the user's whole trained range (21.6), so it suggested no keys at all. It now uses tonic−5 to tonic+14, and when nothing fits it ranks keys by how little they stretch the range instead of returning nothing.
- **The copyright guard caught my own prose field** named `notes`. The field was renamed to `comment` rather than weakening the guard.
- **Atlas content is honest about its basis.** Only rows backed by the sources in the research addendum are `sourced`. Everything else (e.g. most tempo bands, several grooves and vocal patterns) is `hypothesis` and needs validation against curated data. The two evidence rows restate the addendum's summaries of the cited papers; re-read those papers before relying on their specifics.
- **Family grouping is heuristic.** A title spelled two ways (e.g. a split vs joined word) stays as two songs; one shared first word never merges songs.

### Gate/Blocker
- None for AU-03 or AU-03B.
- The user's include/exclude cleanup is still recommended (DNA currently counts all 74 songs).
- Live Seed-VC is still unverified (host memory).

### Do Not Redo
- DNA is computed live; do not add a cached DNA file unless it becomes slow.
- The Atlas JSON is canonical. Regenerate the workbook with `python tools/export_atlas.py` and never hand-edit it.
- Keep the copyright guard strict: rename prose fields rather than loosening forbidden keys.

### Next Action
**AU-04 Song Blueprint Generator:**
- Combine prompt + `GET /artist/dna` (tempo band, key families, loops, form, voice) + `GET /theory/candidates` (era, harmony, groove, vocal, fitted keys) + originality constraints into a structured, editable blueprint.
- Show why each choice was made.
- No audio yet.

## Session 007 — 2026-09-24 — AU-04 Song Blueprint Generator (+ My Voice redesign plan)

### Goal
Build AU-04: prompt + Artist DNA + R&B Theory Atlas + voice range + originality constraints → a structured, editable Song Blueprint (tempo, key, sections, chords as Roman numerals plus chord names, arrangement, energy curve, vocal-range constraints), with the reason for each choice, wired into Create's button. No audio.
Mid-session the user also asked for a plan to make My Voice work like the Kits.ai convert page inside the Auralis shell, added to GitHub.

### Starting State
- `main` at `8b9f1fa`, equal to `origin/main` (nothing to pull).
- The user's uncommitted Harmonic Reference work was still in the tree, so only this session's hunks of `auralis/api/main.py` are staged.
- The user's My Music spot-check and include/exclude cleanup is still pending. The blueprint reads DNA live, so it follows those toggles whenever they are made.

### Changed
- **New package `auralis/composer/`:**
  - `brief.py`: keyword brief reader and lyrics header splitter
  - `chords.py`: keys and Roman numerals → chord names in any key
  - `blueprint.py`: `build_blueprint`, `revise`, `regenerate`
  - `validation.py`: errors and warnings
- **API:** new `auralis/api/composer.py`:
  - `POST /composer/blueprint`, `/revise`, `/regenerate`
  - `PUT/GET /projects/{pid}/blueprint`, `GET …/blueprint/revisions`
  - Included in `main.py` (2 lines).
- **Projects:** `ProjectStore.save_blueprint` / `blueprint` / `blueprint_revisions` write `blueprint.json`, `blueprints/rNNNN.json` and `lyrics.txt`.
- **Atlas:** `theory.key_fit` factored out of `suggest_keys` so the blueprint places vocal registers with the same rule that picks the key. `suggest_keys` behaviour is unchanged.
- **Frontend:**
  - new `BlueprintView.jsx` + `Blueprint.css`
  - `CreatePage.jsx`: the Create button builds a blueprint, and the workspace gains Blueprint / My songs tabs
  - `AtlasPanel.jsx`: controllable, with an Auto era
- **Docs:**
  - new `docs/VOICE_STUDIO_PLAN.md` (Kits-style My Voice plan)
  - architecture doc updated
- **Tests:** new `tests/test_composer.py` (30).

### Verification
- `pytest -q` including the local harmony tests → **153 passed**. Excluding them → 133 passed (103 before + 30 new). `npm run build` passes.
- **Real DNA (74 songs) + trained voice, "Dark late-night R&B, big chorus":**
  - Modern Alternative R&B, minor (from "Dark"), 94 BPM (the DNA median), B♭ minor, 10 sections / 72 bars / about 3:03.
  - First chorus near the DNA's 0:37. The chorus uses the user's own loop, re-voiced `i9 i9 i9 ♭VImaj7`; the other sections use Atlas families.
  - Vocal registers stay inside D3–C5, with a 7-semitone chorus lift.
  - Validation clean, every decision explained.
- **"romantic quiet storm ballad with falsetto":** switched to major and said why ("every 80s R&B / Quiet Storm family in the Atlas is major"), A♭ major, soul-dominant pre-chorus, pedal maj9 chorus.
- **Browser pane (restarted with `stop_auralis.ps1` / `start_auralis.ps1 -NoBrowser`):**
  - Create built the blueprint and showed it with the energy curve and 10 editable section cards.
  - Changing the key to E minor and typing `i9 iv7 ♭VIImaj7 V7` into Verse 1 gave revision 3, "edited: key, sections", and chords Em9 · Am7 · Dmaj7 · B7.
  - No console errors, no horizontal overflow at 1600 px.
- **Not done in the UI:** saving to a project, to avoid adding a test project to the user's real project list. Saving is covered by the store and API tests (revisions, lyrics, survives a new store instance, refused when closed).

### Result
**AU-04 COMPLETE** against its gate: *Auralis can create and edit a complete blueprint with tempo, key, sections, chords, arrangement and vocal-range constraints.* The Kits-style My Voice redesign is **PLANNED ONLY** (`docs/VOICE_STUDIO_PLAN.md`, phases V1–V5); none of it is built.

### Findings
- **The Atlas minor vocabulary is thin.** Only 2 of its 12 progression families are minor (`minor_flat_six_loop`, `dorian_vamp`), while 62% of the user's songs are minor. Minor blueprints therefore lean on the user's own loops and reuse those two families across sections. Adding sourced minor families (minor ii–V, i–iv vamps, ♭VI–♭VII–i cadences, minor-plagal colour) is the most useful Atlas curation next.
- **First-draft problems, fixed before commit:**
  - Verse, pre-chorus and bridge all got the same progression. Each section type now prefers a progression no other type has.
  - Regenerate could hand the chorus another section's chords. It now avoids them.
  - A lyric line starting with "hook" was read as a section header. Headers must now be bracketed or the bare word.
- **Key spelling.** `voice/pitch.parse_key` rejects `G♯`. The composer has its own parser, and the catalog-twin check compares pitch classes, not names.
- Arrangement palettes and role levels are **editorial defaults**, labelled that way in the blueprint. They are not Atlas research.
- Python's text mode on Windows wrote CRLF into `main.py` and three new files during editing. It was converted back to LF (the repo's `.gitattributes` is `eol=lf`), and the diff is unaffected.

### Gate/Blocker
- AU-04: none.
- Still open: the user's BPM/key spot-check and include/exclude cleanup in My Music, and live Seed-VC conversion (host commit memory).
- The My Voice plan has three open questions for the user (§6 of the plan).

### Do Not Redo
- The blueprint schema (v1), the Roman-numeral convention (chromatic from the tonic, major-scale reference) and the decision order are settled. AU-05 reads `sections[].chords`, `groove`, `arrangement`, `energy_curve` and `sections[].vocal`.
- Keys are chosen last from the voice. Do not reintroduce "key of the reference song".
- DNA loops are always re-voiced and limited to one section type. Keep that originality rule.

### Next Action
- **Either** AU-05 MIDI / Structured Composer (blueprint → chords, bass, drums, melodic parts → local instruments),
- **or** My Voice redesign V1–V3 from `docs/VOICE_STUDIO_PLAN.md` if the user wants the Kits-style page first.
- Ask the user which comes first. Curate more minor-mode Atlas families alongside either.

## Session 008 — 2026-09-24 — AU-05 MIDI / Structured Composer + instrumental render

### Goal
The user approved the plans and asked for AU work first, then the My Voice redesign (with voices saved from a microphone take, Kits/Suno style). This entry covers AU-05: blueprint → chords, bass, drums and melodic parts → local instruments → a complete instrumental. My Voice follows in Session 009.

### Starting State
- `main` at `6fe5d70` (AU-04), equal to `origin/main`.
- The user's uncommitted Harmonic Reference work was still in the tree.
- `mido` and `pretty_midi` are not installed. The MIDI writer is hand-rolled rather than adding a dependency.

### Changed
- `auralis/composer/chords.py`: `chord_tones` (intervals and bass for a Roman numeral).
- New `auralis/composer/arrange.py`: keys, pad, bass, drums, fx and melody-guide tracks.
- New `auralis/composer/midi.py`: SMF type-1 writer plus a minimal reader.
- New `auralis/generation/`:
  - `base.py` (provider interface)
  - `synth.py` (local numpy instruments)
  - `__init__.py` (registry, `render_instrumental`, which runs the existing `engine.pipeline.run` for mix and master)
- `auralis/api/composer.py`: `GET /composer/providers`, `POST /composer/render` (background job, one at a time), `GET /composer/render/{job}/file/{name}`.
- `auralis/projects/jobs.py`: an `instrumental-render` job saves stems, pre-master, master, melody guide, MIDI, the rendered blueprint and the mix report into a project.
- `frontend/src/BlueprintView.jsx`: Render instrumental panel.
- Tests: new `tests/test_generation.py` (13). Architecture doc updated.

### Verification
- `tests/test_generation.py`: 13 passed.
- **Ground truth on a full-length render.** The render was a 3:05 blueprint (G♯ minor, 100 BPM, Modern Alternative R&B). Then Auralis's own analysis tools were run on the audio:
  - the drums stem reads **99.4 BPM**
  - keys + bass read **A♭ minor** (the same key as G♯ minor), confidence 0.62
  - on the keys stem, the three strongest pitch classes were all chord tones of the blueprint chord in **38/38** chord windows
  - render and master took 46 s: −12.7 LUFS, −1.0 dBTP, profile `rhythmic-sparse`
- **Browser pane (restarted with the launcher scripts):** Create ("romantic 90s slow jam, falsetto") → Render instrumental.
  - Progress went through arranging, per-part rendering, and mix and master stages.
  - The master played: 3:27, 80 BPM, B♭ minor, −14.1 LUFS, `vocal-forward-rnb`.
  - `/composer/render/{job}/file/master` returned 200 `audio/wav` (54.8 MB).
- Nothing was uploaded; the render uses no samples, downloads or models.

### Result
**AU-05 COMPLETE** against its gate: *Auralis can render a complete instrumental from a blueprint using local instruments.* The instruments are synthesized sketches (FM electric piano, saw pad, synth/808 bass, synth drums). They show the arrangement faithfully, but they are not production-grade sounds.

### Findings
- **Stem levels.** Each stem is peak-normalised on render, and the mixer then sets role levels. Section dynamics survive inside each stem (velocities scale with section energy and arrangement level), but the balance between stems is the mixer's heuristic, not the blueprint's.
- **The melody guide is a guide.** It follows register, scale, chord tones and hook repetition, but it is rule-based and plain. AU-07 will sing it. It is the obvious place for later quality work, such as rhythm vocabulary from the Atlas vocal patterns or DNA phrase lengths.
- **Half-time.** Grooves switch to half-time drums at 118+ BPM, which is what the DNA's double-time caveat suggests for slow jams read at double speed.
- The first draft only comped the first bar of chords longer than a bar (pedal and stasis sections). This was fixed before commit.

### Gate/Blocker
- AU-05: none.
- Still open: the user's My Music spot-check and switch-off cleanup, and live Seed-VC conversion (host commit memory).

### Do Not Redo
- `generation.PROVIDERS` is the renderer boundary. Add better instruments as new providers (a SoundFont/sampler in an isolated venv) instead of editing the arranger.
- The instrumental goes through `engine.pipeline.run` unchanged, with explicit roles. Keep using it.

### Next Action
Session 009: My Voice redesign (V1 layout, V2 history), plus **voices saved from a microphone take** (the user's request: a friend sings into the mic, and Auralis analyses the take and saves the voice).

## Session 009 — 2026-09-24 — My Voice redesign (Kits-style) + voices saved from the microphone

### Goal
The user's request: "save voices just like kits.ai and suno does so if my friend comes over he can just sing on the mic and it will analyze and copy his voice and save it." Build that, plus the planned My Voice layout (plan V1–V3), in the existing console shell.

### Starting State
- `main` at `5279e3e` (AU-05), equal to `origin/main`.
- The user's uncommitted Harmonic Reference work was still in the tree. Only this session's hunks of `auralis/api/main.py` are staged.
- One voice existed: the user's trained studio profile. Live Seed-VC conversion is still unverified on this host (commit memory).

### Changed
- **Backend:**
  - new `auralis/voice/capture.py` (take analysis and reference-window choice)
  - new `auralis/voice/history.py` (`VoiceHistoryStore`)
  - `auralis/voice/profiles.py`: voice-card fields (created_at, created_via, singer_name, consent_at, consent_clip, take_count, last_take; all default, so old profiles load) and `create_from_take`, `add_take`, `rename`
  - new `auralis/api/voices.py`: take check, voice from take, add take, rename, sample playback, history endpoints, `ENGINE_LOCK`, `record_conversion`
  - `auralis/api/main.py`: router include; conversions wait on the engine lock and are recorded to history; a plain explanation for `os error 1455`
- **Frontend:**
  - new `VoicePage.jsx`/`.css` (hero, tabs, Convert queue, voice cards, history)
  - new `VoiceCapture.jsx` (New voice / Record more wizard)
  - new `recorder.js` (AudioWorklet mic capture, in-browser WAV)
  - `App.jsx` mounts VoicePage; the classic VoiceStudio lives under *My voices → Studio tools*
- **Docs and tests:**
  - `docs/VOICE_STUDIO_PLAN.md` §7 build status
  - architecture doc
  - new `tests/test_voice_library.py` (11)

### Verification
- `pytest -q` including the local harmony tests → **177 passed** (157 committed + 20). `npm run build` passes.
- **Browser pane, real app (restarted with the launcher scripts), full mic flow.** The pane has no microphone, so `getUserMedia` was replaced in the page with a synthetic singer: harmonic tones from 196 to 392 Hz with vibrato and breaths. Everything after the microphone was the real code path.
  - Name + singer + consent, then *Start recording*: live meter at −9 dB, the timer and prompts advanced ("Sing a song" at 0:39).
  - *Stop*, then *Check the take*: "Good take", 39 s singing, level −14 dB, room 51 dB below, sample window 20–40 s.
  - *Save voice*: "Saved “UI Test Voice”. Range G3–G4…". **G3–G4 is exactly the simulated 196–392 Hz.** The voice card showed singer, mic, consent time and "works now as an instant voice"; the sample endpoint served a 2.6 MB WAV.
- **Test voice deleted.** The test voice was deleted through the API right after, and only the user's real voice remains. The page's selected voice was set back to it.
- No horizontal overflow at 375 px in any tab.
- The console showed one real bug, fixed and re-checked: stop/unmount closed the AudioContext twice. After the fix, 0 errors through record → stop → record again → stop → tab switch.
- **Not verified live:** a real Seed-VC conversion on this host (memory). The conversion → history → A/B → project path and the one-at-a-time lock are covered by API tests with a fake provider.

### Result
**COMPLETE** for the user's request and plan V1–V3. A guest can sing into the mic, and Auralis checks the take, saves the voice (with consent on record), measures its range and makes it selectable for conversion. Studio training unlocks at 10 minutes of singing. V4 (My Music stems as guide) and V5 (full-song separation) remain planned.

### Findings
- **Instant voice vs trained voice.** A mic voice works at once as a Seed-VC *instant* voice (reference prompt). Kits-level likeness needs the existing studio training, which needs ≥10 minutes of singing. The card says how much more singing unlocks it, and *Record more* adds takes.
- **Consent.** The consent checkbox is required. The spoken consent clip is optional and is stored apart from the dataset. Delete requires typing the voice name, and it removes the sample, takes, dataset, history and model.
- **Singing seconds are approximate.** The frame gate counts decays and short breaths as singing (39 s reported for about 34 s sung). This is fine for the purpose; the dataset segmentation does the precise work.
- Browser processing (echo cancellation, noise suppression, auto gain) is switched off on purpose, because it colours a voice and would train that colour in.

### Gate/Blocker
- None for this work.
- Still open: live Seed-VC conversion (host memory), and the user's My Music spot-check and switch-off cleanup.

### Do Not Redo
- Voice creation from a take goes through the unchanged `create` / `prepare_reference` / `add_recordings`. Extend those; do not fork them.
- `ENGINE_LOCK` is the single gate for Seed-VC conversions. Future voice jobs (guide singer, AU-08) should take it too.

### Next Action
- Try it with a real singer: *My Voice → New voice*.
- Then the roadmap continues: AU-06 Atmosphere Engine, or AU-07 Guide Singer, which would sing the AU-05 melody guide so a saved voice can perform a whole blueprint.
- Plan V4/V5 when wanted.

## Session 010 — 2026-09-24 — AU-06 Atmosphere Engine

### Goal
The user said "Continue", so I took the next roadmap phase, AU-06. Its gate: *a generated instrumental has musically appropriate atmosphere that follows key, tempo and section energy* (roadmap §8).

### Starting State
- `main` at `a5a9753` (Session 009), equal to `origin/main`.
- The user's uncommitted Harmonic Reference work was still in the tree; `main.py` is untouched this session.

### Changed
- **New `auralis/generation/atmosphere.py`:**
  - era palettes and `era_level`
  - `describe`
  - `plan_atmosphere`: bed, drone, pad, shimmer, choir, sparkle, swell and tail, each with a reason
  - `render_atmosphere`: energy-following gains, dark→bright drone filter, long reverb
- **Blueprint:**
  - each section gets an editable `atmos` role with era-shaped defaults
  - `blueprint.atmosphere` holds the palette and `why.atmosphere` the reasons
  - sections added later get the era default
- **Render path:**
  - the synth provider renders an `atmosphere` stem
  - `render_instrumental` mixes it as `other` at −6 dB (FX −2 dB)
  - an Atmosphere MIDI track
  - a 6 s ring-out after the last bar
- **Engine (opt-in extension):** `mixer.mix(..., gain_offsets=)` and `pipeline.run(..., gain_offsets=)`. Without them the mix is byte-for-byte the old one.
- **UI:**
  - an *Atmos* chip on every section card
  - an Atmosphere panel with its reasons
  - the atmosphere stem and a layer list in the render panel
- **Tests:**
  - new `tests/test_atmosphere.py` (9)
  - `test_composer` role set now includes `atmos`
  - the AU-05 length check allows the intended 6 s tail
- Architecture doc updated.

### Verification
- `pytest -q` including the local harmony tests → **186 passed** (166 committed + 20). `npm run build` passes. The staged tree alone gives 166 passed.
- **Ground truth on rendered audio**, isolated per layer and in the mix, over three eras:
  - **Key:** 92.8% of the atmosphere's chroma energy is in the key (E♭ major song).
  - **Energy:** across verse, pre-chorus, chorus and bridge, section loudness follows the planned energy with Spearman ρ = **0.92** in 2000s, modern alternative and Quiet Storm blueprints. Choruses are the loudest sections.
  - **Tempo:** the sparkle arpeggio's onsets sit a median **16 ms** from the eighth-note grid (the detector resolution is about 12 ms).
- **Browser pane (restarted with the launcher scripts):** "moody alt R&B, big chorus, 3 minutes" → Create.
  - The Atmosphere panel and the per-section Atmos chips showed.
  - Render instrumental gave a 3:09 master at −12.7 LUFS with an atmosphere stem (200, 50 MB) and a 20+ line "why" list: air bed, pedals, swells into each lift (with the energy numbers), rising shimmer, dark chorus pad, "ah" texture, bell sparkle.
- The console showed the "closed AudioContext" error from Session 009's recording tests in the same tab. This session used no microphone, and after the Session 009 fix a listener had counted 0 new errors. It is treated as stale.

### Result
**AU-06 COMPLETE** against its gate. The textures are synthesized, like the AU-05 instruments. They are musically placed and explained, but they are not sample-library quality.

### Findings
- **First draft, fixed before commit:** the low drone dominated. Low sines carry far more RMS than filtered pads, so pre-choruses came out louder than choruses (energy ρ was 0.62). The drone is now quieter and hands over to the rising shimmer across the pre-chorus.
- **Bookends are atmosphere-led on purpose.** Intros and outros keep slightly more atmosphere than verses, because atmosphere carries those sections. That is why the energy correlation is measured across the inner sections; including the bookends it is 0.61–0.73.
- The mixer's role targets would put a texture bed as loud as the keys. The opt-in `gain_offsets` fixes that without changing any existing mix.
- **The AU-05 ground-truth test was intermittently failing, and I fixed the test.** One full run failed it. Each blueprint gets a random id, which seeds the arranger, so every render differs slightly. Over 15 random 12-bar renders, the tempo was exact every time, but the key read as the IV key (G for D major) once. That is the detector's known fifth-neighbour ambiguity on short clips (AU-02), not a render error. The test now accepts the key family and adds a stronger check: the keys stem's loudest pitch classes must be chord tones (120/120 chord windows over 10 random renders).
- **One unexplained failure.** One full staged run had a failure after that fix, and the run printed only its summary line. It then passed 4 more full runs (2 with failure details captured), 5 loops of the new-code test files and 3 loops of the older ones. The most likely cause is transient host memory pressure (this machine threw "Unable to allocate" during AU-02), but that is not proven. If it recurs, run `pytest -rf` to name the test.

### Gate/Blocker
- AU-06: none.
- Still open: live Seed-VC conversion (host memory), and the user's My Music spot-check and switch-off cleanup.

### Do Not Redo
- `atmos` is a normal arrangement role: edit it like the others; don't add a second control.
- Keep atmosphere mixing through `gain_offsets`; don't hard-code levels into the stems.

### Next Action
**AU-07 Guide Singer:** lyrics + the AU-05 melody guide → a synthetic dry guide vocal, correctly timed and pitched, which the saved voices (Session 009) can then convert.
- It needs a local singing-synthesis provider, isolated like Seed-VC.
- Check the options and their licences and memory needs first, then ask the user before installing anything large.

## Session 011 — 2026-09-24 — AU-07 Guide Singer V1 + AU-08 full-song pipeline (first live Seed-VC)

### Goal
The user said "continue" without choosing between the two AU-07 options, so I took the recommended one that needs no install: a built-in guide singer. Then I wired AU-08 (guide → saved voice → Pitch Polish → Vocal Finish → song) and verified it live.

### Starting State
- `main` at `33092e3` (AU-06), equal to `origin/main`.
- The user's uncommitted Harmonic Reference work was still in the tree; `main.py` is untouched this session.
- Host commit memory had **14.0 GB free** (5.6 GB at the Session 001 failure). LM Studio was still resident (13 GB) and RAM had about 1.4 GB free.

### Changed
- **New `auralis/voice/guide.py`:** guide score (melody notes + lyric syllables, vowels, onsets, phrases).
- **New `auralis/voice/singing_provider.py`:** provider boundary and the built-in `VocaliseSinger` formant singer.
- **New `auralis/voice/full_song.py`:** `sing_song`, `plan_chunks`, `_pitch_key`.
- **`auralis/api/composer.py`:** `POST /composer/sing` (job `song-vocal`, under the engine lock) and `GET /composer/sing/{job}/file/{name}`.
- **`auralis/projects/jobs.py`:** `song-vocal` jobs save the song, vocals, guide and report into a project.
- **`auralis/voice/seed_vc.py`:** the conversion subprocess output is decoded as UTF-8 with replacement.
- **`frontend/src/BlueprintView.jsx`:** "Sing it in a saved voice" panel under a finished render (voice, quality, progress, song, vocal stages, downloads, save).
- **Tests and docs:** new `tests/test_full_song.py` (7); architecture doc updated.

### Verification
- **AU-07 ground truth.** A 3-minute guide renders in about 2 s. pYIN on the guide gives **90/90** notes within 50 cents of the score, and phrase starts a median 34 ms (max 58 ms) after the score. 138 lyric syllables were mapped to vowels and onsets.
- **First live Seed-VC conversion on this host** (closing AU-00's open check): 12 s of the guide into the trained studio voice through the app's `/voice/convert`.
  - Same length; a median pitch difference of 10 cents from the guide, with 95.7% of frames within 50 cents.
  - It went to the voice's history automatically: one take, "guide_singer_test.wav", which the user can delete.
- **AU-08 live, short song:** a 12-bar song with lyrics.
  - The chain ran in 76 s: one conversion call, 8 notes tuned, song at −13.9 LUFS / −1.0 dBTP.
  - The converted vocal is on the written pitch for **53/53** notes.
- **AU-08 live, full song in the app** (browser pane, restarted with the launcher scripts):
  - Create with 19 lines of original lyrics ("romantic 90s R&B slow jam, big chorus") → Render instrumental (3:06, B♭ minor, 80 BPM) → **Sing it** with the trained voice at Studio quality.
  - Result: 219 notes, 30 tuned, song master −13.9 LUFS / −1.0 dBTP, vocal 3.9 dB over the music. `/composer/sing/{job}/file/song` returned 200 (49.5 MB).
  - The 2.6-minute vocal went through one Seed-VC call. In the first 60 s, **110/110** notes are within 50 cents of the score in both the converted and the finished vocal.
- **Memory during the run:** Seed-VC took about 9 GB of commit (5 GB still free). The whole run took roughly 12 minutes, most of it Pitch Polish's pYIN paging, with 1 GB of RAM free while LM Studio was resident.

### Result
- **AU-07 PARTIAL against its gate** (*given lyrics and the blueprint melody, render a correctly timed/pitched dry guide vocal*). Timing and pitch pass on ground truth, and the lyrics drive the rhythm (one note per syllable) and the vowels. **The built-in singer does not pronounce intelligible words.** That needs a lyric-capable engine (DiffSinger or similar), which the user has not yet chosen to install.
- **AU-08 COMPLETE against its gate** (*an entire lead vocal for an original generated song in the user's trained voice, without the user singing the guide*). Verified live on a full-length song, with the same caveat about words.

### Findings
- **AU-00 open item closed.** Live Seed-VC works whenever commit memory allows; the earlier failure was environmental, as diagnosed.
- **AU-00 gap 2 found and fixed.** Seed-VC prints progress bars; decoding them with the Windows code page crashed Python's output reader thread, which is why failures surfaced as "Unknown Seed-VC error" with empty output. The conversion now decodes as UTF-8 with replacement, as training already did.
- **Pitch Polish is slow on whole songs under memory pressure** (full-rate pYIN). It would be faster tracking at 22.05 kHz; not changed yet, because it alters an existing module's behaviour.
- **Guide bug caught by a test:** "you" was read as an i-vowel (the y counted as a vowel). A word-initial y before a vowel is now a consonant.

### Gate/Blocker
- AU-07 words: needs the user's choice of a singing engine. The DiffSinger code is Apache-2.0, but each English voicebank has its own licence, and it needs GPU memory.
- Still open: the user's My Music spot-check and switch-off cleanup.

### Do Not Redo
- Seed-VC live conversion is verified. Don't re-diagnose memory unless a conversion fails (the error now shows the real message).
- `sing_song` reuses Seed-VC, Pitch Polish, Vocal Finish and the pipeline unchanged; extend it rather than fork them.

### Next Action
- Ask the user whether to add a lyric-capable singer (DiffSinger) for real words.
- Otherwise AU-09 Vocal Production: doubles and harmonies from the lead line, converted through the same voice.

## Session 012 — 2026-09-24 — AU-09 Vocal Production (doubles, harmonies, ad-libs)

### Goal
The user said "continue" (no install choice for a lyric singer), so I took the next roadmap phase, AU-09. Mid-session the user asked to "continue next 20 phases". The roadmap defines four phases after AU-09 (AU-10 to AU-13), plus My Voice V4/V5 from the plan. I told the user that and will work through them in order, proposing new phases afterwards rather than inventing twenty.

### Starting State
- `main` at `11523b5` (Session 011), equal to `origin/main`.
- The user's uncommitted Harmonic Reference work was untouched. The new modules are named `composer/vocal_parts.py` and `voice/vocal_production.py`, not `harmony.py`, to avoid a clash with the user's `engine/harmony.py` (flagged in AU-00).
- Host memory: 9.8–10.5 GB commit free, about 1 GB RAM free (LM Studio resident).

### Changed
- **New `auralis/composer/vocal_parts.py`:** `plan_parts`, producing doubles L/R, a high harmony, a low harmony and ad-libs from the lead score. Each section's amount follows its `backing_vocals` level, capped by the production setting (lead / doubles / harmony / full).
- **New `auralis/voice/vocal_production.py`:** `pack`, `convert_parts` (all parts in as few Seed-VC calls as possible) and `backing_bus` (high-pass, levels, constant-power pan, a room; per-part stems plus a stereo bus).
- **`auralis/voice/full_song.py`:** parts are rendered by the guide singer with separate seeds and converted together with the lead. The backing bus goes into the song mix as `other` +4 dB. New `production` parameter.
- **`auralis/voice/singing_provider.py`:** a little of the pure fundamental is kept under every vowel. Some vowels boosted the 2nd harmonic above it, so pitch trackers read the note an octave up; Seed-VC's own pitch extraction faces the same risk.
- **API and projects:**
  - `POST /composer/sing` takes `production`
  - backing stems are served by `/composer/sing/{job}/file/{part}` and saved into projects
- **UI:** a Vocals choice (Lead only / Lead + doubles / Lead + harmony / Full production), a player per backing stem, the parts' reasons and the engine-run count.
- **Tests and docs:** new `tests/test_vocal_production.py` (7); architecture doc updated.
- The staged tree alone gives 180 passed, and the frontend builds.

### Verification
- `tests/test_vocal_production.py` + `tests/test_full_song.py`: 15 passed. The two failures on the way were in my test data: unscaled noise clipping in a 16-bit WAV, and wrong gap arithmetic in an expectation. Fixed in the tests, not the code.
- **Before the singer fix:** with a stand-in engine, the low harmony was 8/11 on pitch, and all three misses were exact octave errors. After the fix the gate test passes octave-strict in two keys.
- **Live with the trained voice** (12-bar song, full production, Studio quality):
  - all six vocal parts went through **one** Seed-VC call: 117 s for 103 s of singing
  - total run 206 s; song −14.0 LUFS
  - every backing part is on its written pitch in the user's voice: high harmony 10/10, low harmony 10/10, double L 20/20, double R 20/20, ad-libs 10/10
- A one-off 3-key × full-length pitch sweep ran over 20 minutes on the RAM-starved host and was stopped. The pytest gate covers the same check on short songs in two keys.

### Result
**AU-09 COMPLETE** against its gate: *one generated song can produce lead, doubles and harmonies as separate stems.* Verified live, with ad-libs as well. Like the lead, the backing parts carry melody and vowels, not intelligible words.

### Findings
- **Packing all parts into one call is the big win.** Model loading dominates short conversions, and full production cost one Seed-VC run instead of six.
- **The backing mix is heuristic.** Levels and pans are fixed producer defaults, and the mixer then treats the bus as `other`. It is worth user-adjustable levels later.

### Gate/Blocker
- None for AU-09.
- Words still need a lyric-capable singer (the user's choice).

### Do Not Redo
- Convert vocal parts through `convert_parts`, packed, never one call per part.
- Keep backing parts under the lead via the bus (`other` + offset). Don't give them the `vocal` role, which would centre them and push them to lead level.

### Next Action
AU-10 Automatic Song Assembly: one prompt → blueprint → instrumental → vocals → finished WAV, with editable stems kept.

## Session 013 — 2026-09-24 — AU-10 Automatic Song Assembly + AU-12 Retrieval & Similarity Guard

### Goal
Continue the user's "next phases" request, doing the local phases first. AU-10 is one prompt → finished song with editable stems. AU-12 is catalog retrieval plus an originality guard. AU-11 (generative-audio model) and V5 (vocal separation) need model downloads and wait for the user's go-ahead; AU-13 and V4 are next.

### Starting State
- `main` at `9462f5b` (AU-09), equal to `origin/main`.
- The user's Harmonic Reference work was untouched.
- RAM was about 1 GB free (LM Studio resident), which made test runs slow (the staged AU-09 run took 16 min).

### Changed
- **AU-10:**
  - new `auralis/composer/assemble.py` (`save_song_to_project`, `remix_stems`, `remix_project`)
  - `POST /composer/song`, `GET /projects/{pid}/stems`, `POST /projects/{pid}/remix`
  - new `frontend/src/SongStudio.jsx`
  - `CreatePage.jsx`: *Make the whole song* button, Screen-3 stage list, Song tab
- **AU-12:**
  - new `auralis/artist/retrieval.py` and `auralis/artist/similarity.py`
  - `analyze.py`: `melody_notes` factored out of `_melody` (same behaviour)
  - blueprint originality checks include the catalog chord comparison; `_catalog()` carries `roman_per_bar`
  - `POST /artist/retrieve`, `POST /composer/similarity`, blueprint `influence` / `influence_song_ids`
  - UI: Influence choice with song picking; *Check originality* on renders
- **Fix:** `artist_dna`, `/theory/candidates` and the composer's voice lookup use the shared `VOICE_STORE`. Separate store instances broke the API test's isolation; normal use pointed at the same folder.
- **Tests:** new `tests/test_song_assembly.py` (3) and `tests/test_similarity.py` (7); architecture doc updated.

### Verification
- `tests/test_similarity.py` 7 passed. `tests/test_song_assembly.py` passes, including the API gate with a fake voice engine. `test_composer` passes with the new originality check.
- **Real catalog, AU-12:**
  - "dark late-night R&B, big chorus" with Influence *closest* built in 0.3 s. The chord check against all switched-on songs passed with no 8-bar run.
  - After the fallback fix, the five retrieved songs match on tempo 93–98, minor key, groove and chorus lift; the focused DNA centres on 94 BPM, 100% minor.
  - The originality job read 6 lead-vocal stems from the catalog drive (read-only; about 100 s each the first time, then cached) in 596 s.
- **The first melody flag was a false positive.** It flagged 11 notes as matching one song. A shuffled baseline over those same six melodies showed chance runs of 6–11 intervals, and the flagged run was only steps and repeated notes (0, ±2). After the fix, three different takes of that song pass against the six melodies, and the synthetic copies in the tests are still flagged.
- **Browser pane, AU-10** (restarted with the launcher scripts):
  - "short uptempo 2000s R&B", *Closest 5*, voice switched off → *Make the whole song*.
  - The stage list advanced through blueprint, harmony, atmosphere, rendering, mix/master and saving, then opened the Song studio: a master at −14.3 LUFS and 6 stems.
  - Mute FX + drums −3 dB → *Remix and master* gave "✓ Saved remix_01.wav (5 stems, −14.1 LUFS)", listed next to the original master.
  - This left a real project named "short uptempo 2000s R&B" in the user's Projects.
- The sung path of `/composer/song` was verified through the API gate with a fake engine. The live singing chain is the one verified in Sessions 011–012.

### Result
- **AU-10 COMPLETE** against its gate: one prompt travels from blueprint to a downloadable finished WAV, and the editable stems are kept in a project and can be remixed.
- **AU-12 COMPLETE** against its gate: "Continue my sound" retrieves useful characteristics from the catalog, and melodic and chord similarity to prior songs is flagged, with a chance baseline. Audio-fingerprint similarity is not implemented, and the check says so.

### Findings
- **Melody similarity needs a chance baseline.** R&B lead lines use a small interval alphabet (mostly steps and repeats), so long shared step runs are normal between unrelated melodies. A fixed length threshold is misleading.
- **Retrieval from sparse prompts** must fall back to the artist's overall centre, or "closest" collapses to mode alone.
- **Reading a stem set from the network drive costs about 100 s per song** (memory-starved host). Catalog melodies are cached after the first check.

### Gate/Blocker
- AU-11 and V5: need model downloads and licence checks. Ask the user.
- Words for the guide singer: still the user's choice.

### Do Not Redo
- Keep the chance baseline in the melody check; never flag on length alone.
- Remixes go through the project's stems (`remix_project`); don't re-render to change a balance.

### Next Action
AU-13 Demo-to-Song, then My Voice V4 (a My Music lead-vocal stem as the guide). Then ask about AU-11 and V5 models.

## Session 014 — 2026-09-25 — AU-13 Demo-to-Song

### Goal
Continuing the user's "next phases" request: AU-13. Its gate: *a phone-quality voice memo or rough instrumental can become a structured Auralis project with an arrangement that preserves the requested musical idea.*

### Starting State
- `main` at `b4dcbc1` (AU-10 + AU-12), equal to `origin/main`.
- The user's Harmonic Reference work was untouched.

### Changed
- **New `auralis/composer/demo.py`:**
  - `analyse_demo`, `tempo_from_notes`, `fit_tempo`, `key_from_notes`
  - `melody_to_beats`, `harmonize`, `build_from_demo`
- **`auralis/composer/arrange.py`:** a blueprint's `demo.line` is sung in every section of its role.
- **`POST /composer/demo`.**
- **New `frontend/src/DemoPanel.jsx`:** Create's Demo button, which until now only said "later phase". The blueprint shows a "melody from your demo" badge and the demo's reasons.
- **Tests and docs:** new `tests/test_demo.py` (8); architecture doc updated.

### Verification
- `tests/test_demo.py`: 8 passed.
- **Ground truth:** four synthetic memos. Tempo within 0.1 BPM, key correct, all pitches kept, all onsets on their 16th. Covered: 100 BPM D major; 88 BPM F major; 76 BPM A minor; an eighth-note line at 92.
- **Two first-draft failures, fixed before commit:**
  - **Key:** chroma-based detection read the D-major hook as F♯ minor. It is now read from the sung notes against Krumhansl–Kessler profiles, with the final note weighted.
  - **Tempo:** the onset-envelope beat tracker read 88 → 121 and 76 → 114 (4:3 and 3:2) on soft sung attacks, and a 1% error made late notes drift off their 16ths. Tempo now comes from the sung notes' inter-onset intervals, then a ±4% fit to the grid.
- **Browser pane, real app** (restarted with the launcher scripts):
  - A simulated microphone sang the D-major hook into the Demo panel for 21 s → *Build the song around it*.
  - Result: "Built around your demo: 22 notes kept as the chorus at 100 BPM in D major".
  - Chorus chords: Dmaj9 Bm9 Em9 F♯m9 Dmaj9 Bm9 F♯m9 Dmaj9; the badge "chorus melody from your demo" shows.

### Result
**AU-13 COMPLETE** against its gate, for sung or hummed demos: the idea's melody, tempo and key survive exactly into a full blueprint, and from there into the instrumental, vocals and project through AU-05 to AU-10.

### Findings
- **Rough instrumental demos:** chords are harmonized from the melody. Chords actually *played* in a demo are not detected yet, so a demo with its own chords gets a harmonization, not those chords.
- **Timing:** the demo's first note is taken as the bar line. Pickups are quantized as if they started the bar.
- **Sung memos need their own analysis tools:** the notes are a better clock and key source than onset envelopes or chroma.

### Gate/Blocker
- None for AU-13.
- AU-11 (a generative-audio model) and My Voice V5 (vocal separation) need model downloads and licence checks, and wait for the user's go-ahead.

### Do Not Redo
- Demo tempo and key come from the sung notes; don't switch back to onset-envelope beat tracking or chroma for memos.

### Next Action
My Voice V4 (a My Music lead-vocal stem as the conversion guide). Then ask the user about AU-11 and V5 models.

## Session 015 — 2026-09-25 — My Voice V4: a My Music lead vocal as the guide

### Goal
The last local item from the plan, before the phases that need models (AU-11, V5).

### Changed
- **`auralis/api/voices.py`:**
  - `GET /voice/library-guides`: catalog songs that have a lead-vocal stem.
  - `POST /voice/convert-from-library`: reads the stem through `SongAudio`, writes it into the job folder only, then runs the unchanged `_run_voice_conversion` (engine lock and history included).
- **`frontend/src/VoicePage.jsx`:** Convert gets an *Audio input | From My Music* switch.
- **Tests and docs:**
  - `tests/test_voice_library.py`: a V4 test (temporary stem folder, fake engine, catalog snapshot identical afterwards)
  - `docs/VOICE_STUDIO_PLAN.md` §7 and the architecture doc

### Verification
- `tests/test_voice_library.py`: 12 passed.
- **Real app:** From My Music lists **15** of the user's songs with separated lead vocals, and the Convert button names the selected voice.
- **Not run live:** a real conversion of a full-length catalog stem, to spare memory. After the stem is read it takes the same path verified live in Sessions 011–012.

### Result
**V4 COMPLETE** against its gate (a catalog lead-vocal stem converts without writing anything into the catalog folder), verified with the snapshot test.

### Next Action
AU-11 and V5 need model downloads. Ask the user:
- **AU-11:** a local generative-audio model for textures/sections behind the render-provider boundary, or keep the synth.
- **V5:** a local vocal-separation model so full mixes can be guides.
- **Words for the guide singer:** DiffSinger or similar, still open.

### Session 015 addendum — similarity guard fix found by the full test run
- **What failed:** a full run on the pushed code (`d508c9d`) gave 198 passed, 1 failed: `test_gate_melody_copy_is_flagged_original_passes`. The test plants a 40-note copy of a randomly generated melody. When the copied stretch had no leap, Session 013's "must have melodic shape" rule let a plain stepwise copy pass unflagged. It happened intermittently, because each run generates a different melody.
- **Fix:** a run far beyond chance (at least 16 intervals, and twice chance + 2) is flagged whatever its shape. Shorter runs still need both shape and a margin above chance.
- **Checked:**
  - planted copies caught 30/30 over random melodies
  - 10 takes against the real catalog's six cached lead vocals raise no false flags
  - `tests/test_similarity.py` passed 8 runs in a row

## Session 016 — 2026-09-25 — Model research, faster whole-song pitch polish, queue cancel

### Goal
The user said "Continue" without choosing among the model-dependent items (AU-11 generative audio, V5 separation, words for the guide singer). Those need downloads and the user's go-ahead, so this session:
- researched them (licences, hardware) for a one-step decision
- did local backlog items: whole-song pitch polish speed, cancelling queued conversions

### Changed
- **New `docs/MODEL_OPTIONS.md`:**
  - **ACE-Step:** Apache-2.0 code and weights; commercial use OK; about 8–12 GB VRAM, which competes with Seed-VC on the 12 GB card.
  - **MusicGen:** weights CC-BY-NC, non-commercial.
  - **Stable Audio Open:** community licence, free under US$1M revenue.
  - **Demucs:** MIT code, but its weights are for scientific use only.
  - **DiffSinger:** Apache-2.0, but the English voicebanks found are non-commercial unless licensed.
  - Recommendation: words first (with a commercially licensed voicebank); ACE-Step after a model scheduler; V5 deferred until a commercially clean separation model is found.
- **`auralis/voice/pitch.py`:** optional `track_sr` (default unchanged).
- **`auralis/voice/full_song.py`:** 22.05 kHz tracking when the lead sings for more than 2 minutes; `pitch_tracking_hz` in the result.
- **`frontend/src/VoicePage.jsx`:** ✕ to cancel a waiting item in the Convert queue.
- **Docs:** `docs/VOICE_STUDIO_PLAN.md` (V3 now complete) and the architecture doc.

### Verification
- **Pitch polish on the Session 012 converted vocal (known score):**
  - full rate 74.2 s vs 22.05 kHz 30.7 s (2.4×)
  - notes detected 64 vs 55
  - accuracy after polish: 96% vs 94% of notes within 25 cents, median 10 cents for both (raw vocal: 93%)
  - **The first claim that it would find "the same notes" was wrong** (the frame-based thresholds change with the hop), so it is only used automatically for long vocals, with the measured trade-off documented.
- **Queue cancel in the real page, with the engine calls stubbed in the browser:**
  - three files queued, the third cancelled while the first was converting
  - only a.wav and b.wav were sent; c.wav shows "cancelled"
  - a first attempt with instantly finishing stubs raced past the click; retested with 1.5 s jobs
- The test suite run is recorded in the commit.

### Next Action
Waiting for the user's choice in `docs/MODEL_OPTIONS.md`. Otherwise, local improvements:
- demos: chords from a played instrument, and pickup notes
- a model scheduler (roadmap §16), the prerequisite for ACE-Step

## Session 017 — 2026-09-25 — Demo chords and pickups, backing levels, engines and model lifecycle

### Goal
The user chose "Neither yet": no purchase, no DiffSinger voicebank, no ACE-Step download or install, no large model changes. Instead:
- finish the demo improvements: played chords, pickups, adjustable backing-vocal levels, while keeping the pitch-correction and My Voice conversion/cancel behaviour
- build the model lifecycle (unload one heavy model, load another, finish the job, release)
- create clean provider interfaces for ACE-Step sections, a guide singer (DiffSinger or other) and Seed-VC
- keep Create simple and put the advanced controls in Studio
- test everything, document what remains, and commit so another agent can resume

### Starting State
- `main` at `556abb0` (Session 016), equal to `origin/main`.
- The user's Harmonic Reference work was untouched. Only this session's hunks of `auralis/api/main.py` are staged.
- Host: LM Studio resident; 7.5–10 GB commit free during the session.

### Completed
1. **Demos (commit `23485c6`):**
   - **Played chords:** a melody-masked CQT separates what an instrument plays from the sung line (a voice's overtones otherwise look like a major triad). Chords are read per bar and kept as played; unclear bars are harmonized. Demos with chords and no singing work. The key comes from the notes plus the chords read.
   - **Pickups:** from the phrasing, from where played chords change, or set by hand. Pickup notes sound just before the section.
   - Rejected along the way: hiss counted as "an instrument" (fixed with a spectral peak-contrast gate: played notes about 41 dB, hiss about 7.5 dB); a missed first sung note shifting the chord grid (fixed by taking the bar line from the chord changes).
2. **Backing-vocal levels (same commit):** per-part and whole-stack levels when singing, and a rebalance of saved parts in the Song studio without re-singing.
3. **Engines and model lifecycle (this commit):**
   - new `auralis/models/`: `lifecycle.py` (`ModelManager`, the `balanced` / `keep_warm` / `low_memory` policies, memory gate), `interfaces.py`, `builtin.py` (Seed-VC and vocalise adapters; ACE-Step and DiffSinger adapters, not installed), `worker.py` (resident-worker protocol), `registry.py`
   - `api/engines.py`: `/models`, `/models/policy`, `/models/select`, `/models/release`
   - `api/voices.convert_with_voice` replaces `ENGINE_LOCK` for `/voice/convert`, Sing and Make the whole song
   - `sing_song` takes its guide singer from the registry
   - `render_instrumental` sends sections marked `renderer` to a section generator (a `generated` stem)
   - `frontend/src/EnginesPanel.jsx` in Studio → Advanced; a "Render with" choice on blueprint sections appears only if a section generator is installed
   - `docs/MODEL_INTEGRATION.md`
4. **Tests:**
   - demos +7 (voice-only never an instrument; played I–vi–IV–V kept exactly; singing over a quieter instrument; pickups from phrasing, chords and by hand; the API override)
   - backing +3
   - engines +16 (`tests/test_models.py`)
   - `tests/conftest.py`: memory gate off in tests (they use fake engines) and a temporary engines config, so the user's settings are never touched

### Verification
- Demo tests 15/15. Calibrated on synthetic ground truth: voice-only leaves 0.8% residual (no instrument); piano-only reads I vi IV V ×2 exactly with the release tail dropped; voice over a quieter piano reads 7/8 bars; a 1-beat pickup is found from phrasing and from chord changes.
- Engines tests 16/16. A real subprocess worker loads, answers, errors cleanly and is gone after unload. The manager never runs two jobs at once and never holds two resident models.
- Staged tree for the demo/backing commit: **209 passed**, frontend builds.
- Staged tree for this commit: result recorded in the commit message.
- **Real app** (restarted with the launcher scripts):
  - Studio → Advanced shows Engines: Seed-VC installed, vocalise built in, DiffSinger and ACE-Step not installed with their licences and VRAM, the policy selector, 7.5 GB free.
  - The Create page shows no engine or model wording.
- **Preserved behaviour:**
  - pitch correction is unchanged (`pitch_polish` default path; the Session 016 tests pass)
  - the conversion queue and cancel UI is unchanged
  - one-conversion-at-a-time is still tested (`test_conversions_never_run_two_at_once` passes through the model manager)

### What remains (needs the user)
- **Purchases / large downloads (not done, by instruction):**
  - an English DiffSinger voicebank with a suitable licence
  - ACE-Step weights (Apache-2.0, several GB, about 8–12 GB VRAM)
  - a separation model with commercially usable weights for V5 (Demucs weights are non-commercial)
- **Design decision still open:** whether generated sections (ACE-Step) should ever replace the synth by default, or only when chosen per section. Currently per section, off by default.

### What remains (engineering, no purchase needed)
- ~~A live VRAM reading in the engines status~~, done in the follow-up commit: `nvidia-smi` (advisory warning, not a gate). On this host it showed the RTX 4070 with 5.4 of 12.0 GB VRAM free while LM Studio was resident, so Seed-VC (about 6 GB typical) now logs a warning; it has still converted successfully in earlier sessions.
- Demos: seventh chords in played-chord reading; melody extraction from singing over a loud instrument needs separation (V5).
- Backing-vocal level presets per era; lyric phonemes (ARPAbet) for a future lyric singer, which would live in its worker.

### Future integration points (exact)
- **ACE-Step:**
  - `auralis/models/builtin.py::ACEStepSections`
  - provider folder `%LOCALAPPDATA%\Auralis\providers\ace-step\` (`.venv\Scripts\python.exe` + `auralis_worker.py`)
  - worker op `generate_section` (`prompt, seconds, tempo, key, seed, out_dir, stems` → `paths.mix`)
  - selected in Studio → Engines; per-section `renderer: "ace-step"` in the blueprint
  - consumed by `generation.render_instrumental` → `generated` stem
  - tested seam: `tests/test_models.py::test_render_uses_a_section_generator_for_marked_sections_only`
- **DiffSinger:**
  - `auralis/models/builtin.py::DiffSingerGuide`
  - provider folder `providers\diffsinger\`
  - worker op `sing` (`notes` from `voice/guide.GuideNote`, `seconds`, `seed`, `out_path`)
  - selected in Studio → Engines; used by `voice/full_song.sing_song` for the lead and every backing part, inside the model manager before Seed-VC
- **Seed-VC:**
  - `auralis/models/builtin.py::SeedVCConverter` → `voice/seed_vc.SeedVCProvider` (unchanged)
  - entry point `api/voices.convert_with_voice`
- The full guide is in `docs/MODEL_INTEGRATION.md`; licences and hardware are in `docs/MODEL_OPTIONS.md`.

### Do Not Redo
- All heavy work goes through `MODELS.use(...)`; never add another lock or a direct provider call.
- New engines are adapters in `auralis/models/builtin.py`, living in their own venv behind `SubprocessWorker`; never import them into the MIT package.
- Keep engine choices out of Create.
