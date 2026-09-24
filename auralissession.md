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
