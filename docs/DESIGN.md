# LocalMaster — Technical Design Document

**A local-first, autonomous mixing & mastering studio for Windows.**

Status: Draft v0.1 · Owner: Prinze · Last updated: 2026-05-28

---

## 1. Purpose & scope

LocalMaster takes raw audio — either individual stems or a finished stereo mix — and
produces a balanced mix and a release-ready master, entirely on the user's own machine.
No audio ever leaves the desktop. The system is opinionated but transparent: every
decision it makes is inspectable, adjustable, and reversible.

The product targets the same job RoEx's Automix does (per-stem analysis → masking
reduction → EQ/dynamics/panning → stereo mastering → loudness normalization), but runs
offline and is built on an open DSP stack.

### In scope
- Stereo **master-only** path (reference-matched mastering + loudness targeting).
- Multi-stem **mixing** path (classification, masking-aware balancing, EQ, panning, glue).
- **Style profiles** — curated, measurable sonic targets inspired by well-known
  production aesthetics.
- A local web GUI with waveforms, meters, A/B compare, and a per-stem mixer.
- One-click Windows packaging.

### Out of scope (for now)
- Real-time / live mixing.
- Source separation (assume the user provides stems; may add later via Demucs).
- Cloud sync, accounts, collaboration.
- Any claim to clone a specific named individual's process. See §6.

---

## 2. Design principles

1. **Local-first, always.** The default and only required mode is offline. This is both a
   privacy promise and an architectural constraint: no per-job cloud calls.
2. **Transparent over magical.** Every processing stage emits human-readable parameters
   and a report. The user can see *why* a 2.5 kHz dip was applied to the guitar.
3. **Reversible by construction.** Stems are never destructively modified. Processing is a
   parameter set applied at render time; the original files are untouched.
4. **One demonstrable path before breadth.** Master-only ships first and is independently
   useful. Mixing and style profiles layer on top without rewrites.
5. **Honest naming.** Style targets describe *the sound*, not a person. See §6.

---

## 3. System architecture

```
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND — React + Vite (localhost:5173 in dev)              │
│  • Drag-drop stem / mix upload                                │
│  • WaveSurfer.js waveforms + spectrum                         │
│  • Style profile picker (sound cards)                         │
│  • Per-stem mixer strip: gain / pan / mute / solo             │
│  • LUFS + true-peak meters, A/B compare                       │
│  • Job progress via WebSocket                                 │
└───────────────────────────────┬──────────────────────────────┘
                                 │  REST (jobs) + WS (progress)
┌───────────────────────────────▼──────────────────────────────┐
│  BACKEND — FastAPI (localhost:8000)                           │
│  • POST /upload   POST /analyze   POST /mix                   │
│  • POST /master   POST /export    GET  /jobs/{id}             │
│  • WS   /ws/jobs/{id}  (progress events)                      │
│  • In-process asyncio job runner (no external broker)         │
└───────────────────────────────┬──────────────────────────────┘
                                 │  direct Python calls
┌───────────────────────────────▼──────────────────────────────┐
│  DSP ENGINE — the core library (`localmaster.engine`)         │
│  1. analysis   librosa / essentia / pyloudnorm                │
│  2. mixing     masking detection → EQ / level / pan           │
│  3. processing pedalboard (JUCE-backed fx)                    │
│  4. mastering  Matchering (reference matching) + limiter      │
│  5. loudness   pyloudnorm → target LUFS, true-peak ceiling    │
└───────────────────────────────────────────────────────────────┘
```

### 3.1 Why this stack

| Concern | Choice | Rationale |
|---|---|---|
| Audio I/O | `soundfile` / `libsndfile` | Reliable WAV/FLAC; Windows wheels bundle the native lib. |
| Analysis | `librosa`, `essentia` | Spectral features, onset/tempo, classification helpers. |
| Loudness | `pyloudnorm` | ITU-R BS.1770 LUFS measurement and normalization. |
| Processing fx | `pedalboard` (Spotify, MIT) | Studio-grade EQ/comp/reverb/limiter as fast Python objects, JUCE under the hood. |
| Mastering | `Matchering` | Proven open-source reference matching (RMS, FR, peak, stereo width). |
| Backend | `FastAPI` + `uvicorn` | Async, WebSocket-native, trivial to bundle. |
| Frontend | React + Vite + WaveSurfer.js | Rich, responsive GUI with real waveform/meter rendering. |
| Packaging | PyInstaller + bundled static frontend | Single Windows executable, no Python install required. |

None of the core path requires a GPU. Optional ML models (§5.4) are the only component
that benefits from one, and they degrade gracefully to heuristics.

---

## 4. Data model & job lifecycle

A **Project** owns one or more **Tracks** (stems) or a single **Mixdown**, plus the
selected **StyleProfile** and a **RenderSpec**.

```
Project
├── id, name, created_at, working_dir
├── tracks: [Track]            # stems (mixing path)
│   └── id, path, role, analysis, params   # role: vocal|drums|bass|harmonic|other
├── mixdown: Mixdown | None    # stereo input (master-only path)
├── profile: StyleProfile
└── render: RenderSpec         # format, bit depth, target LUFS, peak ceiling
```

**Job lifecycle:** `queued → analyzing → mixing → mastering → normalizing → done | error`.
Each transition emits a WebSocket event `{job_id, stage, pct, message}`. Jobs are
idempotent and write only into the project's `working_dir`; nothing else on disk is touched.

**Provenance guarantee:** on export, the engine also writes `session.json` (every
parameter applied), the isolated processed stems, and a human-readable `report.md`. This
lets the user reproduce or revert any result — a habit the RoEx engineers themselves
recommend.

---

## 5. DSP pipeline

### 5.1 Analysis
For each input, measure: integrated LUFS, true peak, crest factor, spectral centroid,
per-critical-band energy (Bark/ERB), and stereo correlation. For stems, run role
classification (§5.4). Output is a compact `analysis` struct cached on the Track.

### 5.2 Masking-aware mixing (the hard part)
This is where "mixing intelligence" lives.

1. **Pairwise spectral overlap.** For each pair of stems, compute energy overlap per
   critical band. High overlap in a perceptually important band = masking.
2. **Priority ranking.** The style profile assigns each role a priority (e.g. vocal > drums
   > bass > pads). When two stems mask, the lower-priority one gets a gentle complementary
   EQ dip in the contested band; the higher-priority one is left clear.
3. **Level balancing.** Solve relative gains toward the profile's target balance
   (e.g. vocal-to-instrument ratio), constrained so no stem clips the bus.
4. **Panning.** Spread same-role stems across the stereo field per the profile's width
   target; keep bass and lead vocal centered.

Output: a per-stem chain of `[HighpassFilter, PeakFilter(s), Gain, Pan]` expressed as
`pedalboard` objects + a parameter list for the report. **Interpretable, not a black box.**

### 5.3 Bus processing & mastering
Sum stems to stereo (or take the user's mixdown). Apply:
- Glue compression (slow bus comp, modest ratio) per profile.
- **Matchering** against the profile's reference target (FR, RMS, peak, stereo width).
- True-peak limiter to the configured ceiling (default −1.0 dBTP).

### 5.4 Optional ML (graceful fallback)
- **Stem classifier:** small CNN on log-mel features → role label. Fallback: spectral
  heuristics (centroid + bandwidth + onset density) if the model is absent.
- **Future:** a differentiable-mixing-console controller (cf. Steinmetz DMC / Diff-MST)
  that predicts mix parameters end-to-end. Kept behind a flag; the heuristic path is the
  guaranteed baseline so the tool always works without trained weights.

### 5.5 Loudness & export
Normalize integrated loudness to target (default −14 LUFS for streaming; presets for −9
"loud" and −16 "dynamic"). Re-check true peak after normalization. Export WAV/FLAC/MP3 +
the provenance bundle from §4.

---

## 5A. AI / ML components — what runs where

**Important framing:** despite the "AI mixing" label common in this space, the large
majority of LocalMaster is **deterministic digital signal processing** (FFTs, filters,
gain solving, loudness integration) operating directly on audio sample arrays. DSP runs on
CPU, needs no model file, and produces identical output every run. There are exactly three
tiers of actual machine learning in the system, and they use **different runtimes for
different reasons**. Critically: **none of the audio processing is an LLM/GGUF task.**
GGUF + LM Studio serve *language* models that predict text tokens; they have no native
concept of a waveform and cannot mix audio.

### Tier 0 — DSP (no ML, ~99% of the tool)
Matchering, masking detection, EQ/compression/limiting (`pedalboard`), and LUFS targeting
(`pyloudnorm`). CPU-only, deterministic, no model file. This tier is fully functional with
zero AI installed and is what ships in Phase 1.

### Tier 1 — Stem classifier (small audio model, optional)
"Is this stem vocal / drums / bass / harmonic?" A small CNN over log-mel features, run via
**ONNX Runtime** (or PyTorch). Distributed as a `.onnx` / `.pt` file — **not GGUF**. Tiny,
CPU-fine. If the model is absent, the engine falls back to spectral heuristics, so the tool
never hard-depends on it.

### Tier 2 — Mix-parameter controller (audio model, future, flagged)
A differentiable-mixing-console controller (cf. Steinmetz DMC / Diff-MST) that predicts
interpretable mix parameters end-to-end. Also a **PyTorch/ONNX audio model, not GGUF** —
audio ML lives in a separate ecosystem from text LLMs. This is the one component that
benefits from a GPU. Kept behind a flag; the heuristic path remains the guaranteed default.

### Tier 3 — Natural-language control layer (LLM — *this* is where LM Studio fits)
**The only place a GGUF / LM Studio belongs.** Optional. Lets the user type plain-language
requests — *"make the vocal punchier and widen the chorus"* — and have them translated into
engine parameters. The flow:

```
user text ──▶ LLM (local GGUF via LM Studio, OpenAI-compatible API on localhost)
                  │  reads: the analysis struct + current params (JSON in)
                  ▼
            parameter delta (JSON out)  ──▶  DSP engine applies it  ──▶  re-render
```

The LLM **never touches audio samples.** It reads JSON (analysis + current settings) and
emits JSON (a parameter adjustment). The DSP engine validates and executes it. This is a
clean fit for a local-first setup: point the control layer at LM Studio's
OpenAI-compatible endpoint (default `http://localhost:1234/v1`), load any instruct GGUF,
and the tool stays fully offline. If LM Studio isn't running, this layer is simply disabled
and the GUI controls work as normal.

**Summary table:**

| Tier | Task | Runtime | File format | GPU? | Required? |
|---|---|---|---|---|---|
| 0 | All audio DSP | CPU (native libs) | none | no | **yes** |
| 1 | Stem classification | ONNX Runtime / PyTorch | `.onnx` / `.pt` | no | no (heuristic fallback) |
| 2 | Mix-param prediction | PyTorch / ONNX | `.pt` / `.safetensors` | helps | no (flagged) |
| 3 | Natural-language control | **LM Studio (local LLM)** | **GGUF** | helps | no (optional) |

---

## 6. Style profiles ("the sound")

A `StyleProfile` is a **measurable target**, not an impersonation:

```yaml
id: vocal-forward-rnb
display_name: "90s R&B — Vocal Forward"
inspired_by: "The silky, vocal-centric R&B production aesthetic of the era"
targets:
  tonal_curve: curves/rnb_warm.json     # target FR derived from reference analysis
  vocal_to_instrument_db: +3.0
  low_end_weight: warm                   # gentle 80–200 Hz lift
  stereo_width: 0.85
  compression: { bus_ratio: 2.0, character: smooth }
  reverb: { space: plate, amount: 0.18 }
role_priority: [vocal, drums, bass, harmonic, other]
```

Profiles are authored by **analyzing publicly released, commercially mastered tracks** and
reverse-engineering their *measurable* characteristics (tonal balance, width, dynamics) into
target curves. The output is matched to that signature.

**Naming policy.** Profiles are named for the sound ("Maximalist Pop Polish",
"Rhythmic Sparse Low-End", "Vocal-Forward R&B"), with an `inspired_by` note. We do **not**
name profiles after individuals or claim to replicate any person's process. This keeps the
project technically honest (there is no dataset of any individual's per-stem decisions) and
legally clean.

Initial profile set: `pop-maximal`, `vocal-forward-rnb`, `rhythmic-sparse`,
`warm-soul`, `neutral-transparent` (a faithful, character-free master).

---

## 7. API surface (v1)

| Method | Path | Purpose |
|---|---|---|
| POST | `/projects` | Create a project, returns `id` + `working_dir`. |
| POST | `/projects/{id}/upload` | Upload stems or a mixdown (multipart). |
| POST | `/projects/{id}/analyze` | Run analysis; returns per-track structs. |
| POST | `/projects/{id}/mix` | Run masking-aware mixing; returns params. |
| POST | `/projects/{id}/master` | Run mastering + loudness; returns metrics. |
| POST | `/projects/{id}/export` | Render final + provenance bundle. |
| GET  | `/jobs/{job_id}` | Poll job status. |
| WS   | `/ws/jobs/{job_id}` | Stream progress events. |

All endpoints bind to `127.0.0.1` only. No external network listener.

---

## 8. Roadmap

Each phase ends with something demonstrable.

- **Phase 1 — Master-only MVP.** FastAPI + Matchering + loudness export + single-page GUI.
  Upload a stereo mix, pick a profile, download a master. *Independently useful.*
- **Phase 2 — Stem mixing.** Multi-stem upload, classification, masking-aware EQ/level/pan,
  per-stem mixer GUI with meters.
- **Phase 3 — Style profiles.** Profile system + the curated "sound" presets and their
  reference-derived target curves.
- **Phase 4 — Polish.** A/B compare, real-time meters over WebSocket, session reports,
  one-click PyInstaller Windows installer.
- **Phase 5 (optional) — ML controller.** DMC-style parameter prediction behind a flag,
  with the heuristic path remaining the default.

---

## 9. Risks & open questions

| Risk | Mitigation |
|---|---|
| Mixing quality from heuristics is mediocre vs. trained models | Ship master-only first (high quality, low risk); treat mixing as iterative; keep ML path open. |
| Style profiles sound generic | Invest in reference analysis; expose per-profile tuning so power users adjust. |
| Windows packaging of native audio libs (libsndfile, JUCE) | Validate the PyInstaller bundle early, in Phase 1, not at the end. |
| Stem role misclassification | Always allow manual role override in the GUI. |
| Loudness targets vary by platform | Offer presets (−14/−9/−16) and a custom field. |

**Open questions for next iteration:**
1. Do we want optional source separation (Demucs) so users can drop in a stereo song and
   get stems automatically? Adds a heavy dependency and a GPU benefit.
2. Should profiles be user-creatable from a reference track inside the GUI ("learn this
   song's sound")? This is a strong feature but a Phase 3+ scope decision.
3. VST hosting — do we ever want to let users insert their own plugins into the chain?

---

## 10. Repo layout (proposed)

```
localmaster/
├── DESIGN.md                  # this document
├── README.md
├── pyproject.toml
├── localmaster/
│   ├── engine/                # DSP core (pure, GUI-agnostic)
│   │   ├── analysis.py
│   │   ├── mixing.py
│   │   ├── mastering.py
│   │   ├── loudness.py
│   │   └── profiles/          # YAML profiles + reference curves
│   ├── api/                   # FastAPI app
│   │   ├── main.py
│   │   ├── routes.py
│   │   └── jobs.py
│   └── packaging/             # PyInstaller spec, build scripts
├── frontend/                  # React + Vite
│   ├── src/
│   └── ...
└── tests/                     # engine unit tests + golden-file audio tests
```

The `engine` package has **no dependency on the API or frontend** — it is usable as a
plain Python library, which keeps it testable and reusable (and lines up with a
local-infrastructure philosophy).
