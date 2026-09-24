# Auralis Current Architecture

**Audit phase:** AU-00 (baseline audit, see `auralissession.md`)
**Audited:** 2026-09-23
**Baseline commit:** `4910b1c` (GitHub `main`)
**Last updated:** AU-01 (persistent projects), 2026-09-23
**Version in code:** `0.8.0` (`pyproject.toml`, `auralis/__init__.py`, `/health`, `frontend/package.json`)

This document describes what the source code actually does, not what the README
or roadmap says it should do. Every status comes from reading the code, and where
possible from running it in this audit. Test and probe evidence is summarized in
[Tests](#tests) and in the AU-00 entry of `auralissession.md`.

Status vocabulary:

| Status | Meaning |
|---|---|
| **IMPLEMENTED** | Code path exists end-to-end and was exercised by tests or a live probe |
| **PARTIAL** | Works, but part of the described behavior is missing or unused |
| **PLACEHOLDER** | Hook or stub exists; no real behavior behind it |
| **DOCUMENTED-ONLY** | Described in docs/comments; no code |
| **NOT FOUND** | Neither code nor docs |

> **Local uncommitted work (not part of this baseline).** At audit time the working
> tree also held an uncommitted *Harmonic Reference* feature:
> `auralis/engine/harmony.py`, `tests/test_harmony.py`,
> `frontend/src/HarmonicReference.{jsx,css}`, `docs/HARMONIC_REFERENCE.md`, and
> edits to `auralis/api/main.py`, `frontend/src/App.jsx` and `README.md`
> (`POST /harmony/compare`, `GET /harmony/{job_id}/report`). It was preserved
> untouched and was **not** committed with AU-00. It is noted here only because
> its 20 tests ran green alongside the baseline and its routes appeared in the
> live OpenAPI listing. It is a note-domain *analysis* tool. It is not the vocal
> harmony/doubles generator the roadmap plans for `auralis/voice/harmony.py`.

---

## Platform

| Aspect | Actual state |
|---|---|
| Backend | Python ≥3.9 (audited on 3.12.10), FastAPI + Uvicorn, single process, in-memory job table |
| DSP libs | numpy, scipy, soundfile, pyloudnorm (BS.1770), librosa, pedalboard (JUCE), matchering, pyyaml |
| Frontend | React 18 + Vite 8, plain JSX (no TypeScript, router or state library). Mode switching happens in `App.jsx` state |
| Transport | REST (JSON + multipart uploads). Progress over WebSocket `/ws/jobs/{id}` (150 ms poll of the job dict), with REST polling `/jobs/{id}` as fallback |
| Backend port | **8001** (launcher, README, frontend default `VITE_API`). `auralis/run.py` and `docs/DESIGN.md` still say **8000** (drift) |
| Frontend port | 5173 (Vite). CORS allows only `localhost:5173` / `127.0.0.1:5173` |
| Bind address | `127.0.0.1` only (launcher, `run.py`, README) |
| Startup (Windows) | `Run Auralis.bat` runs `tools/start_auralis.ps1`, which checks ports 8001/5173, requires `python` on PATH and Node at `%ProgramFiles%\nodejs`, and runs `npm install` if needed. It starts uvicorn and `npm run dev` hidden, writes PIDs to `%LOCALAPPDATA%\Auralis\runtime\auralis-processes.json`, waits for `/health` plus the frontend, then opens the browser. `Stop Auralis.bat` runs `tools/stop_auralis.ps1`, which kills the saved PIDs and their child trees |
| Console entry | `auralis` script → `auralis.run:main` (port 8000, see drift) |
| Packaging | `auralis/packaging/build_windows.md` is a PyInstaller sketch only. **DOCUMENTED-ONLY** |

### Local directories

| Path | Contents | Lifetime |
|---|---|---|
| `%TEMP%\auralis_jobs\<job_id>\` | Uploads, stems, renders, reports for every job | **Never cleaned up** (no cleanup code exists) |
| `%TEMP%\auralis_voice_profile_*`, `auralis_voice_dataset_*`, `auralis_paired_*` | Upload staging for voice endpoints | Deleted in `finally:` blocks |
| `%LOCALAPPDATA%\Auralis\voices\<profile_id>\` | `profile.json`, `reference.wav`, `dataset/clip_*.wav`, `paired/<id>/`, `model/ft_model.pth` + config | Persistent until the profile is deleted |
| `%LOCALAPPDATA%\Auralis\providers\seed-vc\` | Cloned Seed-VC repo, its own `.venv` (torch 2.4.0+cu121), `checkpoints/` (HF cache, ~3.3 GB), `runs/` | Persistent, installed by `tools/install_seed_vc.ps1` |
| `%LOCALAPPDATA%\Auralis\projects\<project_id>\` | `project.json` + `sources/ stems/ vocals/ mixes/ masters/ reports/ generated/` (AU-01) | Persistent until the project is deleted |
| `%LOCALAPPDATA%\Auralis\runtime\` | Launcher PID file and logs | Per launch |
| `<repo>\checkpoints\` | ~2.4 GB model cache left in the repo root by earlier runs | Gitignored. Not referenced by current code |

### Provider structure

There is one provider boundary today, **Seed-VC** (`auralis/voice/seed_vc.py`):

- It is GPL-3.0, installed separately into its own venv, and never imported into the MIT package.
- Auralis talks to it only through `subprocess` calls to `inference.py` and `train.py`.
- `SeedVCProvider.status()` checks that `.venv\Scripts\python.exe` and `inference.py` exist.

There is no provider base class, registry or scheduler yet. Seed-VC is the
pattern to copy.

---

## Audio Engine

`auralis/engine/` is pure DSP with no API or UI imports. Every module below is
deterministic, and none uses a model.

| Module | Responsibility | Inputs → Outputs | Dependencies | Status |
|---|---|---|---|---|
| `analysis.py` | Per-stem features (LUFS, crest, centroid, bandwidth, flatness, 8-band energy, onset rate, stereo correlation) and role detection. Filename aliases win (confidence 0.98); spectral heuristics are the fallback | `(audio, sr, path, role?)` → `StemAnalysis` | librosa, pyloudnorm | IMPLEMENTED |
| `mixer.py` | Heuristic "Path A" mix: role LUFS targets, profile vocal boost, shared role power budget, role high-pass, pairwise masking EQ dips, same-role pan spread | `[StemAnalysis], profile_id` → `[MixParams]` | numpy | IMPLEMENTED. Profile vocal boosts are hard-coded by profile id, not read from YAML |
| `console.py` | Applies MixParams (HPF, peak EQ, gain, per-role compressor, pan law), resamples to the first stem's SR, sums, then normalizes peak to −3 dBFS headroom | `[(audio,sr)], [MixParams]` → float32 stereo WAV | pedalboard (numpy fallback) | IMPLEMENTED |
| `mastering.py` | `master_file`. Reference resolution order: user reference, then profile bundled reference, then internal-target glue (tonal shelves, bus compressor, M/S width). Loudness stage runs last | WAV path + `StyleProfile` → 24-bit WAV + `MasterResult` | matchering, pedalboard | IMPLEMENTED |
| `loudness.py` | BS.1770 integrated LUFS, 4× oversampled block-wise true peak, iterative gain→limiter→TP-ceiling loop (±0.1 LU, 4 iterations), default ceiling −1.0 dBTP | array → array / `LoudnessStats` | pyloudnorm, scipy, pedalboard | IMPLEMENTED |
| `pipeline.py` | `run()`: analyse → mix → console → master. Writes `pre_master.wav`, `session.json`, `report.md` | stem paths + profile + ref → `MixPipelineResult` | all of the above | IMPLEMENTED. `mode` is always `"heuristic"`. Diff-MST "Path B" is a comment only (**PLACEHOLDER**) |
| `profiles_loader.py` + `profiles/*.yaml` | 5 style profiles (`neutral`, `pop-maximal`, `rhythmic-sparse`, `vocal-forward-rnb`, `warm-soul`) with LUFS target, tonal curve, width, bus compression | id → `StyleProfile` | pyyaml | PARTIAL. `low_end_weight` is declared in every YAML but never read. All `reference:` fields are `null`, so no bundled references exist. `profile_id` is not sanitized before `os.path.join`, which is a low risk on a localhost-only app |

### System classification (the 19 audit items)

| # | System | Status | Evidence |
|---|---|---|---|
| 1 | Stereo mastering | IMPLEMENTED | `test_master_end_to_end`, `test_character_profile_processes_audio`. Live `/upload`→`/master`→`/download` returned 200 with warm-soul hitting its −15.0 LUFS target |
| 2 | Stem mixing | IMPLEMENTED | `test_full_pipeline` and others. Live `/jobs`→3×`/upload-stem`→`/mix` produced −14.0 LUFS / −1.0 dBTP, roles vocal/drums/bass at 0.98, and report, session and WAV downloads all returned 200 |
| 3 | Sound/style profiles | PARTIAL | 5 profiles load (`test_profiles_load`, `GET /profiles`). `low_end_weight` unused. No bundled references |
| 4 | Reference matching | IMPLEMENTED | `test_reference_mode`. Live `/upload-reference` + `use_reference:true` gave `mode: reference`, −14.0 LUFS. Matchering rejects a reference identical to the target (error is surfaced correctly) |
| 5 | Loudness / true-peak | IMPLEMENTED | `test_normalize_hits_target`, `test_ceiling_respected`, `test_limiter_hits_loudness_and_true_peak`. Live mix hit −14.0 / −1.0 dBTP |
| 6 | Voice profile creation | IMPLEMENTED | `test_voice_profile_is_private_and_reusable`, `test_voice_profile_requires_consent`, `test_reference_rejects_clipping`. Live `GET /voice/profiles` shows no private paths |
| 7 | Seed-VC provider | IMPLEMENTED, **but live conversion is blocked on this host** | `GET /voice/provider` → installed. Provider venv: torch 2.4.0+cu121, CUDA available (RTX 4070). The audit conversion failed with Windows `os error 1455` (paging file too small) while loading Whisper, because host commit charge was nearly exhausted by other processes. Not a code defect. See Gaps |
| 8 | Studio Voice dataset handling | IMPLEMENTED | `test_studio_dataset_is_segmented_and_scored`. Live profile: 16.1 min, 137 clips, readiness 72 |
| 9 | Voice training | IMPLEMENTED (not re-run in audit) | `test_mark_studio_training` covers state only. The existing live profile is `studio-trained`, 1000 steps, with `model/ft_model.pth` present. Training was not re-run: it is GPU-hours of work and needs no re-verification for a baseline |
| 10 | Paired calibration | IMPLEMENTED (ingest). Training on pairs is DOCUMENTED-ONLY | `test_paired_calibration_*` (accept/reject). Singer clips are fed into the normal dataset. `docs/PAIRED_CALIBRATION.md` "Future training work" is not in code. The live profile dir contains `model_paired_*`/`paired_training_holdout_*` artifacts that **no current repo code creates** (out-of-repo experiment) |
| 11 | Guide-vocal conversion | IMPLEMENTED (code), unverified live this session | `POST /voice/convert` → `SeedVCProvider.convert` (fast/studio/ultra = 12/35/50 diffusion steps, ±12 st, uses the trained checkpoint when present). Blocked by item 7's host memory issue |
| 12 | Pitch polish | IMPLEMENTED | `test_parse_key_and_detect_c_major`, `test_pitch_polish_corrects_note_centers_and_writes_report`. Live `/voice/pitch`: 8 notes detected, 7 corrected. Download and report returned 200 |
| 13 | Vocal Finish | IMPLEMENTED | 4 tests in `test_vocal_finish.py`. Live `/voice/finish` in rack upload mode: download, preview, report and source all returned 200. `/voice/auto-polish` (pitch→finish) download and preview returned 200 |
| 14 | Instrumental-aware vocal placement | IMPLEMENTED | `finish.analyze_vocal` measures vocal-to-instrument dB and a masking score against an optional instrumental. `_context_mix` renders a placed preview. Pitch Polish uses the instrumental for key detection |
| 15 | Project/job persistence | IMPLEMENTED (AU-01) | Jobs are still in memory plus `%TEMP%`. Since AU-01, finished jobs can be saved into persistent projects (`auralis/projects/`). The project survived a real backend restart with all assets linked (see Persistence) |
| 16 | Frontend/backend communication | IMPLEMENTED | REST + WS as above. No console errors in the browser during the audit |
| 17 | Local model/provider dirs | IMPLEMENTED | `%LOCALAPPDATA%\Auralis\{voices,providers,runtime}` as described above |
| 18 | Tests | IMPLEMENTED (backend only) | 28 committed tests pass. No frontend tests or lint. `npm run build` passes |
| 19 | Windows launcher | IMPLEMENTED (by source review) | The audit started the same commands manually on the launcher's ports (8001/5173). `Run Auralis.bat` itself was not double-clicked |

---

## Voice System

```text
reference WAV (3–30 s, consent checkbox)          POST /voice/profiles
   └─ profiles.prepare_reference: ≥16 kHz, clip check, trim, 44.1k mono, −20 dBFS RMS
      → %LOCALAPPDATA%/Auralis/voices/<id>/reference.wav + profile.json   (kind=instant)

long dry takes                                    POST /voice/profiles/{id}/recordings
   └─ _prepare_dataset_audio → _segment_voice (1.2–20 s phrases, split at quiet)
      → dataset/clip_NNNNN.wav ; analyse_dataset (pyin range, readiness 0–100)
                                                   (kind=studio-dataset)

AI guide + my matching take                       POST /voice/profiles/{id}/paired-calibration
   └─ paired.ingest_paired_calibration: chroma DTW, global slope 0.82–1.18 & sim ≥0.68,
      12 s windows kept if local sim ≥0.74 → paired/<pair>/guide_/singer_*.wav + calibration.json
      singer clips → added to dataset

dataset ≥ 10 min                                  POST /voice/train  (studio=1000 / deep=2500 steps)
   └─ SeedVCProvider.train → provider train.py (44k whisper f0 preset), parses "step N, loss"
      → voices/<id>/model/ft_model.pth + config   (kind=studio-trained)

guide vocal                                       POST /voice/convert
   └─ SeedVCProvider.convert → provider inference.py (+ trained checkpoint if present)
      → TP ceiling −1 dBTP → job/auralis_voice.wav

converted (or any prior-job) vocal                POST /voice/pitch        (natural/studio/modern/hard)
   └─ pitch.pitch_polish: pyin → note segmentation → key (vocal or instrumental, or override)
      → per-note cents edits → rendered WAV + JSON report of every note decision

vocal (prior job or direct upload) [+ instrumental]   POST /voice/finish   (5 presets, intensity, rack modules JSON)
   └─ finish.finish_vocal: analyze → decide → rack overrides (clamped) → HPF/EQ/de-ess/
      serial comp/saturation/double/ambience/output → finished WAV (+ placed preview) + report

one click                                          POST /voice/auto-polish
   └─ pitch_polish(studio) → finish_vocal(polished-pop, 0.75) [+ instrumental preview]
```

Privacy properties the code enforces:

- Consent is required to create a profile. `VoiceProfileStore.create` raises without it.
- Profile ids must match `[a-f0-9]{12}`, which blocks path traversal.
- `VoiceProfile.public_dict()` strips `reference_path`, `checkpoint_path` and `config_path`. The live check found no private paths in the API response.
- `/voice/provider` does return the provider install path, which includes the Windows username. It only goes to localhost.

---

## API Surface

All routes are in `auralis/api/main.py`. Long-running work starts with
`asyncio.to_thread` and reports through `JOBS[job_id]`.

| Area | Endpoint | Purpose |
|---|---|---|
| Meta | `GET /health` | `{"status":"ok","version":"0.8.0"}` |
| | `GET /profiles` | Style profiles |
| Jobs | `POST /jobs` | Empty job (stem mode) |
| | `GET /jobs/{id}`, `WS /ws/jobs/{id}` | Stage / pct / result / error / details |
| Master | `POST /upload` | Stereo mix → new job |
| | `POST /upload-reference/{id}` | User reference track |
| | `POST /master` | `{job_id, profile_id, target_lufs?, use_reference}` |
| Mix | `POST /upload-stem/{id}` | One stem per call |
| | `POST /mix` | `{…, role_overrides: {filename: role}}` |
| | `GET /stems/{id}` | Stems + detected roles |
| Outputs | `GET /download/{id}`, `/download-report/{id}`, `/download-session/{id}` | Master WAV, `report.md`, `session.json` |
| Voice provider | `GET /voice/provider`, `POST /voice/provider/install` | Status / run `install_seed_vc.ps1` (45 min timeout) |
| Voice profiles | `GET/POST /voice/profiles`, `DELETE /voice/profiles/{pid}` | List / create (consent) / delete |
| | `POST /voice/profiles/{pid}/recordings` | Up to 100 dataset files |
| | `POST /voice/profiles/{pid}/paired-calibration` | Guide + singer pair |
| Training | `POST /voice/train` | `{profile_id, depth: studio\|deep}`. Only one training job at a time |
| Conversion | `POST /voice/convert`, `GET /voice/download/{id}` | Guide → my voice |
| Pitch | `GET /voice/pitch-styles`, `POST /voice/pitch`, `GET /voice/pitch/{id}/download\|report` | |
| Finish | `GET /voice/finish-presets`, `GET /voice/rack-modules`, `POST /voice/finish`, `GET /voice/finish/{id}/download\|preview\|report\|source` | |
| Auto polish | `POST /voice/auto-polish`, `GET /voice/auto-polish/{id}/download\|preview` | |
| Projects (AU-01) | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{pid}` | List / create / read (with integrity) / rename or set voice profile / delete |
| | `POST /projects/{pid}/open`, `POST /projects/{pid}/close`, `GET /projects/{pid}/verify?deep=` | Open/close state. Integrity check (existence + size, or SHA-256 when `deep`) |
| | `POST /projects/{pid}/import-job` | Copy a finished job's inputs and outputs in, with provenance. Reference tracks are never imported |
| | `POST /projects/{pid}/assets`, `GET/DELETE /projects/{pid}/assets/{aid}` | Add an audio file directly / download / remove |

Chaining convention: the pitch, finish and auto-polish endpoints take a
`source_job_id` and read `JOBS[src]["result"]["output_path"]`. This is the
only way stages hand audio to each other today. It is in-memory and does not
survive a restart. Saving to a project (`/projects/{pid}/import-job`) is how
outputs become durable.

---

## Frontend Surface

| File | Screen / role |
|---|---|
| `frontend/src/main.jsx` | React root |
| `frontend/src/App.jsx` | Shell with a `mode` state: `home` (mode cards + decorative `SpectralConsole`), `master` and `mix` (4-step `WorkflowRail`: Upload/Stems → Sound → Process → Master, with `InspectorPanel` and `RolePill`), `voice`, `rack`. `API = VITE_API ?? http://127.0.0.1:8001` |
| `frontend/src/VoiceStudio.jsx` | "My Voice Studio": engine status/install, (1) create profile with consent, (2) Studio Voice dataset + paired calibration + readiness + training depth, (3) convert guide, then pitch polish / one-click auto-polish with A/B players |
| `frontend/src/VocalRack.jsx` | Nectar-style module rack (EQ curve, de-ess, comp, saturate, dimension, space, output) over `/voice/finish` with a `modules` JSON body. Assist mode, in/out/mix monitor |
| `frontend/src/ProjectsPanel.jsx` | "My Projects" mode (AU-01): create, list, open/close/delete, assets grouped by kind with players, downloads, provenance, integrity badges, add audio files |
| `frontend/src/SaveToProject.jsx` | "Save to project" control (pick an open project or create one) on the master/mix result, the converted, pitch-polished and studio-polished vocal results, and the Vocal Chain rack result |
| `frontend/src/Knob.jsx` | Rotary control used by the rack |
| `frontend/src/App.css` | Global styling |

Verified live in the browser pane: the home, master upload, stem upload,
Voice Studio (engine ✓, trained profile, readiness 72%) and Vocal Chain screens
all rendered with no console errors. Minor UX finding: Voice Studio briefly
shows **"Install Voice Engine"** and "Create a profile above first" before its
two initial fetches resolve. There is no loading state.

---

## Persistence

| Kind | Where | Survives restart? |
|---|---|---|
| Job state (stage, result, paths) | `JOBS` dict in the API process | **No** |
| Job files (uploads, renders, reports) | `%TEMP%\auralis_jobs\<id>` | Files yes, but unreachable after restart and never cleaned |
| Voice profiles, datasets, paired pairs | `%LOCALAPPDATA%\Auralis\voices\<id>` | Yes |
| Trained checkpoints | `voices\<id>\model\ft_model.pth` (copied from provider `runs\auralis_<id>\`) | Yes |
| Mix provenance | `session.json` + `report.md` per mix job | Yes, as files in temp |
| Song projects (AU-01) | `%LOCALAPPDATA%\Auralis\projects\<id>\project.json` + kind folders | **Yes.** See below |

### Project model (AU-01)

The code is in `auralis/projects/store.py` (`ProjectStore`, `Project`,
`ProjectAsset`), `auralis/projects/jobs.py` (job → asset mapping) and
`auralis/api/projects.py` (router).

- **Manifest.** `project.json` (schema v1) holds id, name, created/updated/opened/closed times, `status` (`open`|`closed`), an optional `voice_profile_id`, `assets[]` and an append-only `history[]`. It is written atomically (temp file + `os.replace`).
- **Assets.** Each asset records id, kind, name, a path relative to the project folder, size, SHA-256, `origin` (upload, or job id + job kind + role) and `metadata` (scalar provenance such as profile, LUFS, key, quality). Files are **copied** in, so the job temp folder can disappear without breaking the project.
- **Open/closed.** A closed project is read-only: adding or removing assets returns 409 until it is reopened.
- **Job mapping.** `jobs.job_outputs`:

  | Job | Becomes |
  |---|---|
  | master | input → `source`, master → `master` |
  | mix | stems → `stem`, pre-master → `mix`, master → `master`, report and session → `report` |
  | voice-conversion | guide → `source`, output → `vocal` |
  | pitch-polish | output → `vocal`, report → `report` |
  | vocal-finish | rack upload → `source`, output → `vocal`, placed preview → `mix`, report → `report` |
  | auto-studio-polish | pitch stage and output → `vocal`, preview → `mix` |

  Mastering reference tracks are never imported.
- **Not yet.** There is no `blueprint.json` or `lyrics.txt` (they belong to AU-04). Jobs do not *start* from project assets yet, so work still flows job → project. A rack-uploaded vocal is saved as `rack_source.wav` because the job does not keep the original filename.

---

## Tests

`pytest -q`: **28 committed tests pass** (18.3 s) at AU-00. After AU-01 there are **42**, with 14 more in `tests/test_projects.py`. The run with the local
uncommitted `tests/test_harmony.py` included gives 48 passed. No frontend tests
or lint scripts exist (`package.json` has only `dev`, `build` and `preview`).
`npm run build` passes (21 modules, ~201 kB JS).

| File | Verifies |
|---|---|
| `tests/test_engine.py` (14) | Profiles load. Normalize hits target. TP ceiling. Limiter hits LUFS and TP together. Master end-to-end. Character profile alters audio. Reference mode. Stem analysis. Filename role priority. Mixer params. Console sums to stereo, preserves centered stereo, handles mixed sample rates. Full pipeline |
| `tests/test_voice.py` (6) | Profile privacy (`public_dict` strips paths) and reuse. Consent required. Clipping rejected. Provider status isolated to its dir. Dataset segmentation and readiness scoring. Training state transitions |
| `tests/test_paired_calibration.py` (2) | Matching performances accepted. Unrelated audio rejected |
| `tests/test_pitch_polish.py` (2) | Key parsing and detection. Note-center correction plus report |
| `tests/test_projects.py` (14, AU-01) | Folders and manifest. Name validation. Copy-not-move. Closed projects are read-only. Survives a new store instance. Verify catches missing and changed files. Id validation. Asset removal. Job mapping for master and mix (reference excluded). Unfinished and non-audio jobs rejected. **API gate test:** master job → project → close → simulated restart → reopen → byte-identical download |
| `tests/test_vocal_finish.py` (4) | Serial compression decision. Rack override clamp, bypass and annotation. `None` overrides are identity. Render + preview + report |

Not covered by tests:

- API routes (no `TestClient` tests, though `httpx` is in dev deps)
- Seed-VC `convert`/`train` subprocess paths
- Launcher scripts
- All frontend code

---

## Reuse Map for Future Create Studio

The generation layer should **feed** these modules, not replace them.

| Future feature | Reuse (existing) | Notes |
|---|---|---|
| **Artist DNA** (AU-02/03) | `engine/analysis.analyse` for spectral, loudness, stereo and onset features. `engine/loudness.measure` for LUFS/TP. `voice/pitch.detect_key`, `_track_pitch`, `_segment_notes` for key and melody contour. `voice/profiles.analyse_dataset` for vocal range and readiness. Pipeline `session.json` as a model of provenance output | New: tempo/structure/chord/section analysis, catalog storage under `%LOCALAPPDATA%\Auralis\artist\`. The local uncommitted `engine/harmony.py` (scale-degree profiles, out-of-key notes) could become a harmony-trait extractor if the user commits it |
| **Song Blueprint** (AU-04) | `voice/pitch.parse_key`, `KeyEstimate`, `SCALES`, `KEY_NAMES` as the shared key vocabulary. `engine/profiles_loader.StyleProfile` for the mix/master target the blueprint selects | New: blueprint schema, validation, lyrics |
| **Composer** (AU-05) | `docs/RECONSTRUCTION_ROADMAP.md` renderer direction (MIDI → local sampler). `engine/console.apply_and_sum` to sum rendered parts | New: harmony, bass, drum and melody generators, MIDI renderer provider |
| **Atmosphere Engine** (AU-06) | `finish._ambience_send`/`_double_send` as simple width and space primitives. `mastering._set_stereo_width` for M/S width. `analysis` role taxonomy (`"other"`/`"harmonic"`) for routing | New: texture generation/assembly |
| **Guide Singer** (AU-07) | `voice/paired` DTW alignment to check a synthetic guide against its target melody. `voice/pitch` note tracking to verify the guide is pitched and timed correctly | New: `voice/guide.py`, `voice/singing_provider.py`, installed as an isolated provider like Seed-VC |
| **My Voice full-song pipeline** (AU-08) | `SeedVCProvider.convert` (with trained checkpoint), then `pitch.pitch_polish`, then `finish.finish_vocal` with instrumental. `_run_auto_studio_polish` already chains pitch and finish | New: long-song chunking and stitching (Seed-VC runs on a whole file; 30 min timeout), plus orchestration from project assets rather than `source_job_id` |
| **Vocal harmonies/doubles** (AU-09) | `pitch._render_edits` (per-note cents shifting), `SCALES`, `finish._double_send`, `SeedVCProvider.convert(semitone_shift=…)` | New: `voice/harmony.py` generator. Naming clash: the uncommitted `engine/harmony.py` is a different concept, so pick distinct names before committing either |
| **Mix/master assembly** (AU-10) | `engine/pipeline.run(stem_paths, role_overrides, profile_id, reference_path, target_lufs)` exactly as is. Pass generated stems with explicit `role_overrides` so detection is not needed. `master_file` for a pre-mixed bounce | New: route project stems into the pipeline, keep them editable |

Rules carried forward:

- Keep Seed-VC and every future heavy model behind a subprocess/venv provider in `%LOCALAPPDATA%\Auralis\providers\`.
- Keep `engine/` free of API imports.

---

## Gaps

**Missing (planned by the roadmap):**

- ~~Persistent song projects~~, done in AU-01. Still missing: starting jobs *from* project assets, and blueprint/lyrics files.
- Artist DNA, music-library import, retrieval, similarity guard.
- Song blueprint, lyrics, composer, MIDI rendering, atmosphere, generative-audio providers.
- Guide singer, vocal harmony/doubles generator, full-song voice orchestration.
- A generic provider interface/registry and a GPU/model scheduler. The audit hit exactly the memory contention this is meant to prevent (see below).
- Diff-MST "Path B" mixer (comment-only placeholder).
- Windows one-file packaging (documented sketch only).

**Defects and drift found (not fixed in AU-00, which is documentation only):**

1. **Host memory blocks live Seed-VC conversion.** Windows `os error 1455` (paging file too small) happened while loading Whisper weights. Commit charge was 5.6 GB free of a 63.7 GB limit, with LM Studio resident. Free memory or enlarge the page file before voice work.
2. **Seed-VC failure diagnostics can be empty.** Through `SeedVCProvider.convert` the same failure surfaced as `Voice conversion failed: Unknown Seed-VC error`, with both stdout and stderr empty. Running the command directly showed the real traceback. Consider logging the full subprocess output to the job dir.
3. **Job directories are never cleaned up.** `%TEMP%\auralis_jobs` grows forever, and `upload_reference`'s docstring promises a cleanup that does not exist.
4. **Port drift.** `auralis/run.py` (the `auralis` console script) and `docs/DESIGN.md` use 8000. The launcher, README and frontend use 8001, so the `auralis` command does not work with the frontend's default.
5. **Stale text.**
   - The `api/main.py` module docstring says "Phase 1 — master-only".
   - `docs/DESIGN.md` is titled "LocalMaster".
   - `docs/RECONSTRUCTION_ROADMAP.md` says "Auralis 0.3".
   - The commit `6e28bbc` message says 0.5 while code is 0.8.0.
   - The README hard-codes an `E:\Auralis` path.
6. **Unused profile field.** `low_end_weight` exists in all 5 YAMLs but no code reads it. Mixer vocal boosts are hard-coded by profile id.
7. **Unsanitized `profile_id` in `load_profile`.** It goes straight into `os.path.join`. Low risk (localhost only, must end in `.yaml`), but it is inconsistent with the voice-profile id validation.
8. **Voice Studio has no loading state.** It flashes "Install Voice Engine" before the status fetch resolves.
9. **Out-of-repo paired-training artifacts.** `model_paired_*` / `paired_training_holdout_*` in the live profile dir and `runs/auralis_<id>_paired_*` in the provider have no producing code in the repo. That experiment is not reproducible from `main`.
10. **Untracked 2.4 GB `checkpoints/` in the repo root.** It is gitignored and not referenced by current code, and is probably a leftover from running Seed-VC with the repo as its working directory.
