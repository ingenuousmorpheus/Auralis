# Auralis Current Architecture

**Audit phase:** AU-00 (baseline audit, see `auralissession.md`)
**Audited:** 2026-09-23
**Baseline commit:** `4910b1c` (GitHub `main`)
**Last updated:** AU-13 Demo-to-Song (Session 014), 2026-09-25
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
| `%LOCALAPPDATA%\Auralis\voices\<profile_id>\` | `profile.json`, `reference.wav`, `dataset/clip_*.wav`, `paired/<id>/`, `model/ft_model.pth` + config. Since Session 009 also `takes/take_NNN.wav` (raw microphone takes), `consent.wav` (optional spoken consent, never trained on) and `history/` (`index.json` + one folder per kept conversion: `output.wav`, `input.*`, cached waveform peaks) | Persistent until the profile is deleted |
| `%LOCALAPPDATA%\Auralis\providers\seed-vc\` | Cloned Seed-VC repo, its own `.venv` (torch 2.4.0+cu121), `checkpoints/` (HF cache, ~3.3 GB), `runs/` | Persistent, installed by `tools/install_seed_vc.ps1` |
| `%LOCALAPPDATA%\Auralis\projects\<project_id>\` | `project.json` + `sources/ stems/ vocals/ mixes/ masters/ reports/ generated/` (AU-01) | Persistent until the project is deleted |
| `%LOCALAPPDATA%\Auralis\artist\library\library.json` + `artist\analyses\<song_id>.json` | My Music index (catalog folders, songs, file fingerprints) and one analysis per song (AU-02). Catalog audio is **not** copied here | Persistent until the folder is removed from the library |
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
| `mixer.py` | Heuristic "Path A" mix: role LUFS targets, profile vocal boost, shared role power budget, role high-pass, pairwise masking EQ dips, same-role pan spread. Optional `gain_offsets` ({path: dB}, AU-06) shift a stem after its role target; without it the mix is unchanged | `[StemAnalysis], profile_id` → `[MixParams]` | numpy | IMPLEMENTED. Profile vocal boosts are hard-coded by profile id, not read from YAML |
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
| 7 | Seed-VC provider | IMPLEMENTED. **Live conversion verified in Session 011** once commit memory allowed (about 14 GB free; a conversion takes about 9 GB). Earlier: blocked | `GET /voice/provider` → installed. Provider venv: torch 2.4.0+cu121, CUDA available (RTX 4070). The audit conversion failed with Windows `os error 1455` (paging file too small) while loading Whisper, because host commit charge was nearly exhausted by other processes. Not a code defect. See Gaps |
| 8 | Studio Voice dataset handling | IMPLEMENTED | `test_studio_dataset_is_segmented_and_scored`. Live profile: 16.1 min, 137 clips, readiness 72 |
| 9 | Voice training | IMPLEMENTED (not re-run in audit) | `test_mark_studio_training` covers state only. The existing live profile is `studio-trained`, 1000 steps, with `model/ft_model.pth` present. Training was not re-run: it is GPU-hours of work and needs no re-verification for a baseline |
| 10 | Paired calibration | IMPLEMENTED (ingest). Training on pairs is DOCUMENTED-ONLY | `test_paired_calibration_*` (accept/reject). Singer clips are fed into the normal dataset. `docs/PAIRED_CALIBRATION.md` "Future training work" is not in code. The live profile dir contains `model_paired_*`/`paired_training_holdout_*` artifacts that **no current repo code creates** (out-of-repo experiment) |
| 11 | Guide-vocal conversion | IMPLEMENTED, **verified live in Session 011**: the AU-07 guide converted into the trained voice, 53/53 notes still on the written pitch | `POST /voice/convert` → `SeedVCProvider.convert` (fast/studio/ultra = 12/35/50 diffusion steps, ±12 st, uses the trained checkpoint when present). Blocked by item 7's host memory issue |
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

### Guide singer and full-song vocal (AU-07/08, Session 011)

- **`voice/guide.py`** builds the guide score. It takes the AU-05 melody guide notes and lines the section lyrics up with them: phrases are split at rests of at least half a beat, and each phrase gets one lyric line and one syllable per note. `syllabify` splits at vowel groups and keeps silent final e's. Each note records its syllable, a vowel (a e i o u uh) and an onset class (hiss / stop / soft; a word-initial y is a consonant). `phrases()` gives the sung spans.
- **`voice/singing_provider.py`** is the provider boundary (`SingingProvider`, `get_singer`). **`VocaliseSinger`** is built in and needs no install. It is a formant singer:
  - a band-limited glottal-style source with 40 ms portamento, vibrato after 150 ms on held notes, jitter and breathiness
  - three vowel formants per note, crossfaded over 30 ms
  - hiss and stop onsets, and a breath before each phrase
  - the output is dry mono at 44.1 kHz, about −20 dBFS RMS with peaks below −3 dBFS
  It sings the melody and the lyrics' rhythm and vowels, **not intelligible words** (`sings_words = False`). A lyric-capable engine (e.g. DiffSinger, isolated like Seed-VC) plugs in behind the same interface.
- **`voice/full_song.sing_song`** runs the chain: guide score, guide vocal, the chosen voice through an injected `convert`, `pitch_polish` (`natural`, key from the blueprint via `_pitch_key`), `finish_vocal` (`smooth-rnb`, 0.7, against the render's pre-master), then `engine.pipeline.run` over the render's stems plus the vocal (role `vocal`, the atmosphere and FX offsets kept).
  - It arranges with the render's seed, so the vocal melody is the same one the instrumental was built around.
  - Vocals up to 6 minutes are converted in one Seed-VC call. Longer ones are cut in the middle of rests into pieces of about 4 minutes (`plan_chunks`).
- **`SeedVCProvider.convert`** now decodes the subprocess output as UTF-8 with replacement. Seed-VC's progress bars used to crash the output reader under the Windows code page, which is why failures surfaced as "Unknown Seed-VC error" (gap 2, now fixed).

### Demo-to-song (AU-13, Session 014)

`composer/demo.py`:
- **`analyse_demo`:**
  - Melody notes come from the library's `analyze.melody_notes` (pYIN at 16 kHz).
  - **Tempo from the sung notes** (`tempo_from_notes`: the densest inter-onset interval, folded into 65–145 BPM), then `fit_tempo` searches ±4% for the tempo that puts onsets on the eighth-note grid. The librosa beat tracker is only a fallback: on soft sung attacks it gave 3:2 and 4:3 readings.
  - **Key from the notes** (`key_from_notes`: duration-weighted pitch classes against Krumhansl–Kessler profiles, the last note counted extra). Chroma of a sparse memo read D major as F♯ minor.
  - A tempo or key the user sets wins.
- **`melody_to_beats`** quantizes to a 16th grid, with the first note on the bar line.
- **`harmonize`** gives one key triad per bar holding the most melody (by length, strong beats and root), starting and ending on the tonic and avoiding a third bar of the same chord; era colour comes from `blueprint._colour`.
- **`build_from_demo`** builds the normal blueprint with the demo's tempo and key, sets every `role` section to the demo's length (4–16 bars) with those chords (`source: "demo"`), and stores the demo as `blueprint.demo.line` (the key is named `line` because the validator forbids `melody` and `notes` keys, which keep third-party material out). `arrange` puts that line into every `role` section and writes melodies only for the others.

### Song assembly (AU-10) and retrieval / originality (AU-12), Session 013

- **`composer/assemble.py`:**
  - `save_song_to_project` creates a project with the blueprint and every stem. Each asset carries `metadata.part` and `metadata.mix_role` (drums, bass, keys/pad → harmonic, fx/atmosphere/backing_vocals → other, lead_vocal → vocal), plus MIDI, the melody guide, the individual backing parts, the guide vocal, and the song pre-master and master.
  - `remix_stems` lists the newest asset per mixable part (individual backing parts are excluded; the bus carries them).
  - `remix_project` rebuilds the master from those files with per-stem gain, mute and solo (solo wins), through the unchanged `engine.pipeline.run` with the default atmosphere/FX/backing offsets, and adds `remix_NN.wav` as a new master.
  - This closes the AU-01 gap: work can now start *from* project assets.
- **`artist/retrieval.py`:**
  - `retrieve(target, songs, analyses, n, picked)` scores switched-on songs by tempo (allowing half/double time), mode, key family, groove, chorus lift and stem-set reliability; picked songs come first.
  - `focused_dna` runs `build_dna` over just those songs.
  - In the API, a target the prompt doesn't fill falls back to the whole-catalog DNA's tempo, mode, groove and lift, so "closest" means your most typical songs that match the prompt.
- **`artist/similarity.py`:**
  - `harmony_check`: the blueprint's chord per bar, reduced to Roman triads, against every song's `roman_per_bar`, as the longest identical run. 8+ bars is *info*, 16+ is a *flag*. It runs inside the blueprint's originality checks on every build and edit, via `_catalog()`.
  - `melody_check`: interval sequences (transposition-free) of the take's melody guide against catalog lead vocals, which `catalog_melody` extracts with the library's own `analyze.melody_notes` and caches in `artist/melodies/<song>.json`.
  - **A flag needs a run clearly above chance** (`chance_run`: the 95th percentile over deterministic shuffles, plus 3) **and a real melodic shape** (3+ different intervals, a skip of 3+ semitones, not mostly repeats). **Or** a run so far beyond chance (at least 16 intervals, and twice chance + 2) that even a plain stepwise copy counts (Session 015 fix). On the real catalog, shuffled melodies share step runs of 6–11 intervals by chance, so a fixed threshold gave a false positive.
  - Audio is not compared, and the check says so.
- **API stores:** `artist_dna`, `/theory/candidates` and the composer's voice lookup now use the app's shared `VOICE_STORE` instead of new store instances.

### Vocal production (AU-09, Session 012)

- **`composer/vocal_parts.plan_parts(blueprint, lead_score, production)`** writes the backing parts as guide scores:
  - two doubles (the lead +12 ms and −8 ms, sung as separate performances)
  - a high harmony (nearest chord tone 3–9 semitones above, else a diatonic third)
  - a low harmony (nearest chord tone 3–9 below)
  - ad-libs (a five-note falling run into rests of at least 1.5 beats after phrases, in the last chorus and the outro)
  Each section's tier comes from its `backing_vocals` level (light = doubles, medium = + high harmony, full = + low harmony and ad-libs), capped by `production`. Harmony notes always stay in the key and inside the voice range (a semitone under the top). Reasons go to `parts_why`.
- **`voice/vocal_production`:**
  - `convert_parts` **packs** the sung spans of every part (lead included) back to back with 1.5 s gaps into as few Seed-VC calls as possible (≤ 6 min each), then unpacks them to their positions. A short song converts in one model load.
  - `backing_bus` high-passes each backing part at 180 Hz, sets its level (doubles −5, harmonies −7/−8, ad-libs −6 dB) and constant-power pan (doubles ±0.75, harmonies ±0.35, ad-libs +0.2), adds a short room, and writes each part plus the summed stereo `backing_vocals` bus.
- **In `sing_song`:** each part is rendered by the guide singer with its own seed, converted with the lead, and the bus joins the song mix as role `other` (so the mixer dips it in the vocal band) with a +4 dB offset.
- **Guide singer change:** the fundamental is kept at 17.5% under every vowel. Without it, some vowel/pitch pairs had a formant-boosted 2nd harmonic that pitch trackers read an octave up; Seed-VC's own f0 extraction faces the same risk.

### Microphone voices and history (Session 009)

- **`voice/capture.analyse_take`** checks a take in 50 ms frames:
  - level (median of the sung frames)
  - room floor (quietest 10%) and SNR
  - clipping, and singing seconds (frames well above the floor)
  - the reference window: the 6–20 s stretch with the most singing and the steadiest level, with clipping ruled out
  It returns a quality (`great` / `good` / `usable` / `retake`), plain-language issues and tips, and `usable`.
- **`VoiceProfileStore.create_from_take`** refuses without consent or with an unusable take. It creates the voice from the reference window via the unchanged `create` / `prepare_reference`, records singer, `created_via="microphone"`, `consent_at` and the optional consent clip, then calls **`add_take`**. `add_take` keeps the raw take in `takes/` and feeds it to the unchanged `add_recordings` segmentation and range/readiness analysis. New profile fields default, so older `profile.json` files still load.
- **`voice/history.VoiceHistoryStore`** keeps finished conversions per voice. The index is written atomically; files are copied, never moved. `_run_voice_conversion` calls `api/voices.record_conversion` when a conversion finishes.
- **One conversion at a time.** `api/voices.ENGINE_LOCK` wraps `SeedVCProvider.convert`; waiting jobs show "waiting for the voice engine". An `os error 1455` / paging-file failure now carries a plain explanation.

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
| Voice library (Session 009, `api/voices.py`) | `POST /voice/takes/check` | Analyse a take without saving: level, room noise, singing seconds, the chosen reference window, issues and tips |
| | `POST /voice/profiles/from-take` | Name + singer + consent + take (+ optional spoken consent clip) → a saved voice and its take report. 422 without consent or when the take cannot make a good voice |
| | `POST /voice/profiles/{id}/takes`, `PATCH /voice/profiles/{id}`, `GET /voice/profiles/{id}/reference` | Add a microphone take to a voice / rename / play the voice's sample |
| | `GET /voice/library-guides`, `POST /voice/convert-from-library` | V4: catalog songs with a lead-vocal stem / convert that stem (read-only, summed into the job folder) through the normal conversion path, into history |
| | `GET /voice/history?profile_id=`, `GET /voice/history/{pid}/{take}/audio?which=output\|input`, `…/peaks`, `PATCH`/`DELETE …`, `POST …/to-project` | Kept conversions (all voices without `profile_id`), audio, waveform, rating/note, delete, copy into a project |
| Projects (AU-01) | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{pid}` | List / create / read (with integrity) / rename or set voice profile / delete |
| | `POST /projects/{pid}/open`, `POST /projects/{pid}/close`, `GET /projects/{pid}/verify?deep=` | Open/close state. Integrity check (existence + size, or SHA-256 when `deep`) |
| | `POST /projects/{pid}/import-job` | Copy a finished job's inputs and outputs in, with provenance. Reference tracks are never imported |
| | `POST /projects/{pid}/assets`, `GET/DELETE /projects/{pid}/assets/{aid}` | Add an audio file directly / download / remove |
| My Music (AU-02) | `GET /artist/library` | Folders + song table (summary per song) |
| Artist DNA (AU-03) | `GET /artist/dna?voice_profile_id=` | Traits across songs switched on in My Music, computed live on every call (tempo, key families, harmony loops, form and lift, groove, melody, voice fit, production) with evidence and confidence |
| R&B Atlas (AU-03B) | `GET /theory/eras`, `GET /theory/sources` | Era list; the source table |
| | `GET /theory/candidates?era=&section=&harmony=&vocal=&groove=&n=&use_voice=&use_dna=` | Several documented, transposable harmony / vocal / groove candidates for an era, each with sources and status; keys fitted to the trained voice range and the DNA key families |
| Song Blueprint (AU-04) | `POST /composer/blueprint` | Prompt + lyrics + optional era / harmony / vocal / groove / key / tempo / length, with `use_dna`, `use_voice`, `artist_dna_weight`, `seed` → a complete, explained blueprint (not saved) |
| | `POST /composer/blueprint/revise` | `{blueprint, changes}` with `title`, `tempo`, `key`, `lyrics`, `sections` (ids to keep, patches, new types) → re-derived blueprint; 422 on invalid edits |
| | `POST /composer/blueprint/regenerate` | `{blueprint, section_id}` → new chords for that section type (all of its sections); nothing else changes |
| Instrumental (AU-05) | `GET /composer/providers` | Render providers (today: `synth`, local numpy instruments) |
| | `POST /composer/render` | `{blueprint, seed, provider, master}` → background job `instrumental-render` (one at a time): arrange → MIDI → stems → mix + master. Progress via `/jobs/{id}` |
| Sing (AU-07/08/09) | `POST /composer/sing` | `{blueprint, render_job_id, profile_id, quality, production}` (production: lead / doubles / harmony / full) → background job `song-vocal` (one at a time): guide score → guide singer → Seed-VC (under the engine lock) → Pitch Polish (blueprint key) → Vocal Finish (`smooth-rnb`, against the instrumental) → song mix and master with the render's stems. 409 when the render came from another blueprint |
| | `GET /composer/sing/{job}/file/{name}` | `song`, `song_mix`, `vocal` (finished lead), `backing` (stereo bus), `double_l`, `double_r`, `harmony_high`, `harmony_low`, `adlibs`, `polished`, `converted`, `guide`, `preview`, `report`. Saving uses `/projects/{pid}/import-job` |
| Song (AU-10) | `POST /composer/song` | Blueprint fields + `profile_id` (none = instrumental only), `production`, `quality`, `project_name` → background job `song-assembly`: blueprint → instrumental → vocals → master, all saved into a **new project** (stems tagged with their mix role, blueprint.json, lyrics.txt) |
| | `GET /projects/{pid}/stems`, `POST /projects/{pid}/remix` | The project's mixable stems / rebuild the master from them with `{levels: {asset_id: {gain_db, mute, solo}}}` (job `project-remix`), saved as `remix_NN.wav` |
| Demo (AU-13) | `POST /composer/demo` | Multipart demo (WAV/FLAC/OGG/MP3, ≤ 3 min) + `prompt`, `lyrics`, `role` (chorus / verse / bridge), optional `tempo`, `key`, `era`, `use_dna`, `use_voice` → a blueprint whose `role` sections keep the demo's melody and carry chords written under it |
| Retrieval + originality (AU-12) | `POST /artist/retrieve` | `{bpm, mode, picked, n}` → the closest switched-on songs with reasons |
| | `POST /composer/similarity` | `{blueprint, seed}` → job: chords vs every switched-on song, the take's melody guide vs the closest lead vocals (extracted once, cached), audio not compared |
| | `POST /composer/blueprint` `influence` | `all` (whole-catalog DNA, default) / `closest` / `picked` + `influence_song_ids`: the DNA is focused on those songs, listed in `inputs.influences` and `why.influence` |
| | `GET /composer/render/{job}/file/{name}` | `master`, `mix`, `midi`, `melody_guide`, `report`, or a stem (`drums`, `bass`, `keys`, `pad`, `fx`). Saving uses `/projects/{pid}/import-job` |
| | `PUT/GET /projects/{pid}/blueprint`, `GET /projects/{pid}/blueprint/revisions` | Save (open projects and valid blueprints only) / read the current blueprint / list saved revisions |
| | `GET /artist/library/songs/{song}/preview` | Player audio: a full mix streams from its folder; a stem set is summed once into a cached 16-bit mixdown under `artist\previews\` (never in the catalog) |
| | `POST /artist/library/sources`, `DELETE /artist/library/sources/{sid}`, `POST /artist/library/rescan` | Add a catalog folder (scans it) / forget one (folder untouched) / rescan |
| | `GET /artist/library/songs/{song}`, `PATCH /artist/library/songs/{song}` | Song files + full analysis / include-or-exclude for Artist DNA |
| | `POST /artist/library/analyze` | Background job over pending/stale songs (or given ids). Progress via `/ws/jobs/{id}`. One at a time |

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
| `frontend/src/App.jsx` | **Console shell (UI redesign, 2026-09-24):** `Sidebar` + page + `PlayerBar`. Pages: `create`, `music`, `studio`, `voice`, `projects`, and tools `master`, `mix`, `rack`, plus `harmony` only when `HarmonicReference.jsx` exists in the checkout (`import.meta.glob`, so the build never depends on it). `API = VITE_API ?? http://127.0.0.1:8001` |
| `frontend/src/Shell.jsx` | `Sidebar`: 3D gold AURALIS wordmark that morphs on press, nav, tools, the trained voice card from `/voice/profiles`. `PlayerBar`: plays catalog songs through `/artist/library/songs/{id}/preview` |
| `frontend/src/CreatePage.jsx` | Suno-style Simple/Advanced create panel (description or lyrics + styles, suggestions from real catalog aggregates, Era & style, Artist DNA / my-voice switches) beside the workspace. **Create builds a Song Blueprint (AU-04)**, and the workspace switches between *Blueprint* and *My songs*. **Make the whole song** (AU-10) runs the one-click job with a Screen-3 stage list and opens the result in the Song studio. An *Influence* choice (all my songs / closest 5 / songs I pick) steers the DNA; in pick mode, clicking songs on the right picks them (AU-12). No audio is rendered yet, and the page says so |
| `frontend/src/DemoPanel.jsx` | Create's *Demo* button (AU-13): record the idea with the mic (the My Voice recorder) or choose a memo; it becomes the chorus, a verse or the bridge; an optional BPM; *Build the song around it* opens the blueprint, badged "melody from your demo" |
| `frontend/src/SongStudio.jsx` | Song studio (AU-10, roadmap Screen 4) on a project: the masters with players and downloads; stems with player, level (−12…+12 dB), mute and solo; *Remix and master*; *Edit blueprint* |
| `frontend/src/BlueprintView.jsx` + `Blueprint.css` | The editable blueprint (AU-04): title, tempo, key (24 keys), meter and length, groove, an energy-curve chart, and one card per section. Each card has type, bars, move/copy/remove, chord chips with Roman numerals, a Roman-numeral text field, harmony options, "New" chords, chords per bar, energy, arrangement role levels and the vocal register. Below: vocal constraints, arrangement palette, originality checks. "Why?" on every decision; save to an open or new project. Every edit calls `/composer/blueprint/revise`. A *Render instrumental* panel (AU-05) renders the blueprint, shows progress, plays the master, stems and melody guide, downloads WAV/MIDI, offers *New take* (next seed), warns when the blueprint changed since the render, and saves the render to a project |
| `frontend/src/DnaPage.jsx` | "Artist DNA" page (AU-03): a card per trait with its headline, confidence, a small visual (tempo bands, key families, loops, forms, writing range drawn inside the trained voice range), a note, and playable evidence songs; the weighting rules in plain words |
| `frontend/src/AtlasPanel.jsx` | Collapsible "Era & style" panel in Create's Advanced mode (AU-03B): Era (with *Auto*), Harmony, Vocal approach, Groove; shows Atlas candidates with the key suggested for the user's voice, sourced/hypothesis badges and source links. Since AU-04 Create controls it, so its choices feed the blueprint |
| `frontend/src/MasterMix.jsx` | The master / mix-from-stems workflow (same API calls as before), restyled |
| `frontend/src/StudioPage.jsx` | Hub for the finishing tools and My Voice |
| `frontend/src/theme.css`, `frontend/src/ui.jsx` | Theme tokens (void black, brushed gold `#d4af5f`, holo cyan `#7fe6ff`; Michroma / Manrope / JetBrains Mono), effects (metallic logo, light-sweep headings, gold corner brackets, scanlines, all off under reduced motion). The theme also remaps App.css's old tokens so older screens turn gold. `ui.jsx` holds icons, cover tiles and `catalogStats` |
| `frontend/src/VoicePage.jsx` + `VoicePage.css` | **My Voice (Session 009), Kits-style layout.** Hero: voice tile, kind, range, readiness, singer, sample player, Switch voice, + New voice. Tabs: *Convert* (drop up to 5 vocals, quality, pitch shift, one-at-a-time queue with progress, output list), *My voices* (voice cards: Use, Record more, Train studio model at ≥10 min, Rename, Delete by typing the name; classic Studio tools below), *New voice*, *History* (all voices), *Harmonies* (disabled until AU-09). The selected voice is remembered in `localStorage` |
| `frontend/src/VoiceCapture.jsx` | *New voice* / *Record more* wizard: voice name, singer, consent (+ optional spoken consent clip), guided take with live meter, clipping warning, timer and prompts, playback and waveform, *Check the take*, *Save voice*. A file can be used instead of the mic |
| `frontend/src/recorder.js` | Microphone capture: AudioWorklet (ScriptProcessor fallback) with echo cancellation, noise suppression and auto gain **off**; 16-bit mono WAV encoded in the browser, so the backend needs no ffmpeg. Stop/cancel are idempotent |
| `frontend/src/VoiceStudio.jsx` | The classic "My Voice Studio", now shown inside *My voices → Studio tools*: engine status/install, (1) create profile with consent, (2) Studio Voice dataset + paired calibration + readiness + training depth, (3) convert guide, then pitch polish / one-click auto-polish with A/B players |
| `frontend/src/VocalRack.jsx` | Nectar-style module rack (EQ curve, de-ess, comp, saturate, dimension, space, output) over `/voice/finish` with a `modules` JSON body. Assist mode, in/out/mix monitor |
| `frontend/src/ProjectsPanel.jsx` | "My Projects" mode (AU-01): create, list, open/close/delete, assets grouped by kind with players, downloads, provenance, integrity badges, add audio files |
| `frontend/src/SaveToProject.jsx` | "Save to project" control (pick an open project or create one) on the master/mix result, the converted, pitch-polished and studio-polished vocal results, and the Vocal Chain rack result |
| `frontend/src/MyMusic.jsx` | "My Music" mode (AU-02): catalog folders, analyse-with-progress, filterable song table (BPM, key, form, vocal range, DNA include toggle), song detail (tempo/key/loudness facts, energy curve with section timeline, top progressions, rhythm, lead-vocal range and phrasing, stem balance) |
| `frontend/src/Knob.jsx` | Rotary control used by the rack |
| `frontend/src/App.css` | Styling of the older screens (VoiceStudio, VocalRack); colours now come from `theme.css` tokens |

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
  | instrumental-render (AU-05) | stems → `stem`, pre-master → `mix`, master → `master`, melody guide / MIDI / rendered blueprint → `generated`, mix report → `report` |

  Mastering reference tracks are never imported.
- **Blueprint (AU-04).** `save_blueprint` writes `blueprint.json` (current) and `blueprints/rNNNN.json` (every saved revision), plus `lyrics.txt` when the blueprint has lyrics. It logs to history and refuses closed projects.
- **Not yet.** Jobs do not *start* from project assets yet, so work still flows job → project. A rack-uploaded vocal is saved as `rack_source.wav` because the job does not keep the original filename.

---

## My Music library (AU-02)

The code is in `auralis/artist/library.py` (scan, group, load, `LibraryStore`),
`auralis/artist/analyze.py` (`analyse_song`), `auralis/artist/__main__.py`
(CLI: `python -m auralis.artist add|scan|analyse|list`) and
`auralis/api/artist.py` (router).

**Catalog handling.** Folders are indexed **in place** and only ever read.

- Grouping rules:
  - a `.zip` of audio is one stem-set song
  - a folder with 2+ named stems is one stem-set song, with its other audio (demo, vocal guide, full mix) attached as `reference`
  - any other audio file is its own song
  - a `.txt` beside a song is linked as its lyrics (path only; the text is not copied)
- Stem roles come from file names: `lead_vocal`, `backing_vocal`, `vocal`, `drums`, `bass`, `harmonic`, `other`. This covers numbered stem-export names (`0 Lead Vocals.wav`), KITS `_drums_KITS_` names, and `(Bass)`-style names.
- A KITS `_backing_KITS_` file is an **instrumental**, not a backing vocal.
- A lone stem among song versions is skipped and counted, not treated as a song.
- Variant tags come from titles: instrumental, remix, cover, demo, type-beat, live.
- Zip members are extracted one at a time to a temp folder and deleted immediately. Stems are summed as they are read, to bound memory.
- Rescans keep analyses of unchanged songs and mark changed ones `stale` (by file size fingerprint).

**Analysis** (`ANALYSIS_VERSION = 3`, deterministic DSP). Stems are used when present, which is why stem sets give the best data. Stems more than 30 dB below the loudest stem are **ignored** (`stems_ignored`): an empty or bleed-only "Lead Vocals" export must not look active or invent a melody. `global.vocal_melody_found` says whether a usable lead melody was extracted (`None` for full mixes). It is **not** an instrumental flag: KITS folders whose vocal lives only in the demo also report `False`.

| Area | Method | Output |
|---|---|---|
| Global | BS.1770 + TP via `engine/loudness.measure`; 3 s short-term loudness spread; M/S ratio | LUFS, true peak, loudness range, crest, stereo width |
| Tempo | librosa beat tracker on the **drums stem** (else the mix), folded into 65–145 BPM, then refined by a line fit through all beat times (the tracker's own tempo is quantised to ~5 BPM steps) | BPM, grid BPM, raw tracker BPM, half/double alternates, stability, pulse clarity |
| Bars | downbeat phase = strongest low-end onsets every 4 beats | bar grid, bar count |
| Key | `voice/pitch.detect_key` on **bass + harmonic stems** (no drums or vocals), else the mix | key, confidence, source |
| Energy | per-bar RMS, 5–95% normalised | energy curve |
| Harmony | beat-synced CQT chroma (+ bass-stem chroma for roots), 24 triad templates, half-bar resolution | chords per bar, roman numerals vs key, change rate, vocabulary, top 4-bar progressions, diatonic share |
| Structure | **stems:** novelty on per-bar stem activity + timbre, sections labelled by similar arrangement. **Mix:** novelty on chroma + timbre, sections labelled by aligned bar-by-bar repetition. Adjacent same-label sections are merged | sections with bars, times, energy, per-stem activity, letter form, role guesses (intro/verse/pre-chorus/chorus/bridge/instrumental/outro, where chorus = repeated + most backing vocals + energy) |
| Rhythm | onset positions within beats (drums stem, else percussive HPSS) | onsets per beat, on-beat/8th/16th shares, syncopation, swing position |
| Melody | pYIN on the **lead vocal stem** (16 kHz); none reported under 5% voiced frames | range (5–95%), centre, phrases and median length in beats, interval profile (repeat/step/skip/leap, rising share) |
| Production | 8-band spectrum, centroid; per-stem RMS | band balance, low/sub ratio, instrumentation balance, vocal-to-music dB |

Role guesses are always labelled as guesses in the data (`roles_are_guesses`)
and in the UI.

---

## Artist DNA (AU-03)

`auralis/artist/dna.py` (`build_dna`, `DNA_VERSION = 1`). Pure aggregation of the AU-02 analyses; nothing is generated.

- **Which songs count.** Only analysed songs switched on (`included`) in My Music. Stem sets weigh 1.0, full mixes 0.7; covers ×0.3, type-beat packages ×0.5. Versions of one song (vocal / instrumental / remixes, grouped by `family_key`) share one song's weight.
- **Traits.** Tempo (weighted quartiles, 10-BPM bands, double-time caveat); keys by **signature family** (relative major/minor together) plus the exact keys as a detail; harmony loops per mode with rotations merged (`canonical_loop`), vocabulary, change rate, diatonic share; form (common chorus-bearing forms, first chorus time, intro bars, section lengths, chorus energy lift; stem sets count double); groove (syncopation, density, swing); melody (lead-vocal stems only); production (LUFS, LRA, width, low-end share, vocal-to-music); voice fit (writing range vs the trained profile's range, headroom and footroom).
- **Honesty rules.** Every trait carries `confidence` (strong / moderate / weak by evidence count), and most carry `evidence` (the songs contributing most). Headlines say when a trait is spread out rather than claiming a favourite.

---

## R&B Theory Atlas (AU-03B)

`auralis/theory/`: data layer only, no generation (research addendum in `auralissession.md`).

- **Canonical data:** `auralis/theory/data/rnb_atlas.json`: 6 eras, 12 progression families (Roman numerals only), 12 chord colours, 6 vocal-phrase abstractions, 6 groove/pocket profiles, 3 section-lift profiles, 2 abstract evidence rows, 12 sources.
- **Status.** Every row carries `status`. `sourced` means the claim is in a cited paper or course. `hypothesis` means an editorial starting point still to be validated. A `sourced` row may not cite only the editorial placeholder.
- **Copyright boundary** (`schema.validate_atlas`, run on every load; the load fails on any problem):
  - no `melody`, `notes`, `midi`, `lyrics`, `audio` or `transcription` keys anywhere
  - progressions are 2–8 Roman-numeral tokens (absolute chord names are rejected)
  - vocal patterns hold single anchor degrees, never sequences
  - every row needs known sources
- **Retrieval** (`atlas.candidates`): the top-n progression families for the era, boosted by section and harmony colour, plus vocal patterns, grooves, section lift and chord colours, each with sources.
- **Keys** (`atlas.suggest_keys`): keys are chosen last. The lead spans from the dominant below the tonic to a step above the octave (tonic−5 to tonic+14), with a semitone of headroom; keys in the artist's DNA key families are preferred. When nothing fits, keys are ranked by how little they stretch the range and it says so.
- **Cheat sheet:** `tools/export_atlas.py` regenerates `docs/research/RNB_THEORY_ATLAS.xlsx` (7 sheets: Era Profiles, Progression Families, Chord Vocabulary, Vocal Phrase Patterns, Groove - Pocket, Song Evidence, Sources) from the JSON, or CSVs with `--csv` or when openpyxl is absent. **The JSON is canonical**; the workbook is never edited as a second source of truth.

---

## Song Blueprint (AU-04)

`auralis/composer/`: a structured, editable song plan. No audio and no melody.

- **`brief.py`.** `parse_brief` is a deterministic keyword reader, not a language model. It picks up era, harmony colour, vocal approach, groove, tempo ("92 BPM"), tempo feel (slow jam / uptempo), key ("in F♯ minor"), mood → mode, length ("3:10", "short"), bridge / no bridge and "big chorus". Every match is recorded in `heard` with the words that caused it. Explicit settings override words (`set_by_you`). `parse_lyrics` splits lyrics on bracketed or bare headers (`[Verse 1]`, `Chorus:`).
- **`chords.py`.** Keys and Roman numerals. Numerals are chromatic from the tonic on the major scale, the same convention as the Atlas and the library analysis, so `♭VI` and `iv6` are explicit. `realise` turns a numeral into a chord name in any key (`IV/V` in A♭ → `D♭/E♭`, `V9sus` → `G9sus4`), spelled with the key's sharps or flats.
- **`blueprint.py`.** `build_blueprint` decides in this order:
  - mode: the key asked for, mood words, the DNA's minor share, or the requested era's Atlas modes
  - era: asked for, or the best fit by tempo, mode, vocal and groove
  - tempo: asked for, or the DNA median moved into the era/feel band (trying half and double time)
  - form: lyrics headers, or R&B defaults shaped by the DNA's pre-chorus/bridge habits, intro bars, first-chorus time and chorus length, then fitted to the target length
  - harmony per section type (below)
  - key **last**: `theory.suggest_keys`, voice range first, DNA key families second
  - groove: the Atlas profile holding the tempo, plus the DNA's syncopation
  - arrangement: per-section role levels, an era palette labelled *editorial*, a mix profile, the Atlas section lift
  - energy: verse floor, chorus lift from the DNA, final chorus peak, pre-chorus ramps, outro fade
  - vocal registers per section inside the voice range (`theory.key_fit` gives the tonic's octave)
- **Harmony options.** Per section type, the Atlas families in the song's mode (in-era first, other eras at a penalty) and the artist's own DNA loops are ranked together by `artist_dna_weight`. DNA loops are **re-voiced** with the era's chord colours (triads → 7ths/9ths), never used as detected.
- **Originality rules.** Only one section type may use a DNA loop. Each type prefers a progression no other type has. The chorus never repeats the verse. `originality.checks` reports: no melody, lyrics or audio carried over; DNA loop reuse; verse/chorus contrast; and a catalog-twin check (same tempo ±2 BPM, key and form as one of the user's switched-on songs).
- **Editing.** `revise(blueprint, changes)` applies edits and re-derives chord names, start bars and times, duration, energy curve, vocal registers, originality and validation. `regenerate` picks the next option for one section type.
- **`validation.py`.** Errors: tempo 40–220, 4/4 only, a parsable key, known section types, 1–64 bars, energy 0–1, chords per bar ½/1/2 (¼ accepted), Roman numerals only (no absolute chord names), role levels off/light/medium/full, 12 minutes at most, and none of the Atlas's forbidden keys (melody, notes, midi…) anywhere except the user's own lyrics. Warnings: peaks at the top of the range, crowded lyric lines, a tonic chord of the opposite mode, and flagged originality checks.

Every decision writes a sentence to `why` (per field) or to the section's `why`, naming the words, DNA trait or Atlas row behind it.

---

## Structured Composer and instrumental render (AU-05)

- **`composer/arrange.py`** turns a blueprint into note tracks, deterministic per seed. A note is `(start_beat, length_beats, midi_pitch, velocity)`.
  - *keys:* rootless voicings for rich chords, placed so each chord moves as little as possible from the last (E3–E5). The comping rhythm follows the section's keys level and repeats every bar of a long chord.
  - *pad:* sustained voicings (C4–D6) where the pad is on.
  - *bass:* root or slash bass (B♭1–A2), a pattern by level and DNA syncopation, and a chromatic approach into the next chord at full level. 808-style long notes when the era palette has an 808.
  - *drums:* General-MIDI patterns by Atlas groove feel (hip-hop, straight, laid-back, deep pocket, swing, half-time at 118+ BPM). Density comes from the arrangement level. Ghost notes in laid-back feels, fills into choruses, crashes on arrivals.
  - *fx:* risers into choruses, impacts on chorus arrivals, a downlifter at the outro.
  - *melody:* a **guide** lead line inside each section's vocal register and the key's scale. Chord tones fall on strong beats, with steps between. Choruses arch to the peak and repeat a hook cell. With lyrics, each line is one phrase with one note per estimated syllable. It is written from rules and the seed only; no song's melody is an input. It is **never mixed into the instrumental**, and the guide singer (AU-07) will use it.
- **`composer/midi.py`:** type-1 Standard MIDI File writer (tempo/meter track plus one named track per part, GM programs, drums on channel 10) and a minimal reader used by tests. No dependency.
- **`generation/`:** the provider boundary from roadmap §7. `RenderProvider` / `RenderResult` are in `base.py`; the `PROVIDERS` registry is in `__init__.py`.
  - `synth.py` (`SynthRenderer`) uses numpy instruments only: FM electric piano, detuned-saw pad, synth and 808 bass, a synthesized drum kit, FX sweeps, and a plain "oo" tone for the melody guide. It applies swing on off-beat sixteenths, the Atlas per-part timing offsets, seeded ±3 ms humanising and a synthetic-IR reverb (overlap-add, memory-light). It writes 24-bit stereo stems.
  - `render_instrumental` validates the blueprint, arranges it, writes `arrangement.mid` and `blueprint.json`, renders stems, then runs **`engine.pipeline.run`** unchanged, with explicit roles (drums/bass/keys→harmonic/pad→harmonic/fx→other) and the blueprint's `mix_profile`. It writes `render.json`.
- **Atmosphere (AU-06), `generation/atmosphere.py`.**
  - *Blueprint side:* every section's arrangement has an `atmos` level (off / light / medium / full), editable like the other roles. Its default comes from the section type, shifted by the era's taste (`era_level`: modern alternative R&B +1, 70s soul and neo-soul −1; a verse keeps at least *light*). `blueprint.atmosphere` holds the era palette (`describe`, labelled *editorial*) and `why.atmosphere` the reasons, including the DNA stereo width.
  - *`plan_atmosphere`* turns the blueprint into layers, each with timing, pitches, gain and a reason:
    - a whole-song **bed** (vinyl crackle, air or room tone by era)
    - a tonic-and-fifth **drone** under intros, verses and outros, fading out across pre-choruses as the shimmer takes over
    - a wide **pad** on the chords in choruses, bridges and interludes (glass, warm or dark by era)
    - **shimmer** (high chord tones, rising through pre-choruses)
    - an "ah" **choir** texture (formant-filtered) in full-level big sections, where the era uses one
    - an eighth-note bell **sparkle** arpeggio (ping-pong)
    - a reversed **swell** that ends exactly on the downbeat of every section that lifts the energy
    - a **tail** of the last chord
    Old blueprints without `atmos` get the era default.
  - *`render_atmosphere`* follows the energy curve per bar: layer gains, and the drone's filter blends from dark to bright as the energy rises. It adds a longer synthetic-IR reverb.
  - *Mixing:* the synth provider writes an `atmosphere` stem. `render_instrumental` mixes it as role `other` with **−6 dB** (and FX −2 dB) through the new `gain_offsets`, and writes an *Atmosphere* MIDI track of the pitched layers. Renders now run 6 s past the last bar so the tail rings out.
- **Speed and memory:** a 3:05 blueprint renders and masters in about 46 s. Parts render one at a time, so peak memory stays near one stereo stem.

---

## Tests

`pytest -q`: **28 committed tests pass** (18.3 s) at AU-00. After AU-01 there are **42**, with 14 more in `tests/test_projects.py`. After AU-04 there are **133** committed tests (153 with the local harmony tests). After AU-05, **146** (166). After Session 009, **157** (177). After AU-06, **166** (186). After Session 011, **173** (193). After AU-09, **180** (200). After Session 013, **190** (210). After AU-13, **198** (218). The run with the local
uncommitted `tests/test_harmony.py` included gives 48 passed. No frontend tests
or lint scripts exist (`package.json` has only `dev`, `build` and `preview`).
`npm run build` passes (21 modules, ~201 kB JS).

| File | Verifies |
|---|---|
| `tests/test_engine.py` (14) | Profiles load. Normalize hits target. TP ceiling. Limiter hits LUFS and TP together. Master end-to-end. Character profile alters audio. Reference mode. Stem analysis. Filename role priority. Mixer params. Console sums to stereo, preserves centered stereo, handles mixed sample rates. Full pipeline |
| `tests/test_voice.py` (6) | Profile privacy (`public_dict` strips paths) and reuse. Consent required. Clipping rejected. Provider status isolated to its dir. Dataset segmentation and readiness scoring. Training state transitions |
| `tests/test_paired_calibration.py` (2) | Matching performances accepted. Unrelated audio rejected |
| `tests/test_pitch_polish.py` (2) | Key parsing and detection. Note-center correction plus report |
| `tests/test_composer.py` (30, AU-04) | Brief words and explicit overrides. Lyrics headers (a lyric line starting with "hook" is not a header). 11 Roman-numeral realisations; key parsing. **Gate:** a complete blueprint: tempo, key, 4/4, intro to outro, chords filling every bar, arrangement roles, energy curve, vocal registers inside the voice, chorus above verse, a reason for every decision. No melody keys anywhere. DNA loops re-voiced and used once; chorus differs from verse. Key fits the voice and DNA; a narrow voice gets an honest stretch. An era without the DNA's mode follows the era. Tempo from DNA, half-time, prompt. Form from lyrics and length. Works with no DNA and no voice. Catalog twin flagged. Edits to key, tempo, sections and chords re-derive everything; invalid edits reported; regenerate changes one section type only. Save with revisions and lyrics, survives a new store, refused when closed. API: create, revise, 422, regenerate, save, read |
| `tests/test_demo.py` (8, AU-13) | **Gate (ground truth):** four synthetic voice memos (no click, hiss added): a D-major hook at 100 BPM, the same hook in F at 88, an A-minor hook at 76, an eighth-note line at 92. Each gives the tempo within 1 BPM, the right key, every pitch kept and every onset on its 16th. The blueprint keeps the demo as every chorus (arranged melody = demo), chords written under it hold ≥70% of the notes, and the rest of the song exists. Harmonizer and key helpers; a clear error when there is no melody; API upload and a 422 for an invalid role |
| `tests/test_song_assembly.py` (3, AU-10) | A song saved to a project with the blueprint and mix-role-tagged stems (individual backing parts not double-remixed), deep-verified. Remix with mute, level and solo; all-muted is refused; it works from a new store instance. **Gate (API):** one request → project with a downloadable finished WAV and editable stems → remix job → blueprint readable |
| `tests/test_similarity.py` (7, AU-12) | Roman reduction and longest run. Retrieval ranks by closeness, counts double time, ignores switched-off songs, puts picks first. Focused DNA uses only its songs. **Gate:** a chord-for-chord copy is flagged (also inside the blueprint's own checks) while an unrelated song passes; a transposed 40-note melody copy is flagged while a different melody passes; step-only runs at chance level and repeated notes are never flagged |
| `tests/test_vocal_production.py` (7, AU-09) | Parts follow the sections' backing-vocals levels and the production cap (lead = none, doubles = doubles only). Harmonies are 3–9 semitones from the lead, chord tones, in key and in range; doubles are the lead a few ms apart; ad-libs sit only in rests at the end. Pack/unpack restores exact positions and splits long calls. **Gate:** each rendered part is on its written pitch (≥90%, octave-strict, two keys); a song produces the lead, two doubles (panned left/right), two harmonies, ad-libs and the bus as separate files from one conversion call; "lead" production gives no backing |
| `tests/test_full_song.py` (7, AU-07/08) | Syllables, vowels and onsets ("you" is soft, not an i-vowel). The score lines lyric syllables up with melody notes; no lyrics gives vocalise. **Gate (AU-07, ground truth):** the rendered guide is dry mono at about −20 dBFS, ≥90% of notes within 50 cents of the written pitch (pYIN), phrase onsets within a 60 ms median. Chunk planning (whole when short; long vocals cut only inside rests). Key spelling for Pitch Polish (G♯ minor, D♭ major…). End-to-end `sing_song` with a stand-in voice: every stage file, a stereo song at the render's length, ≤ −0.9 dBTP. API: 404 unknown voice/render, 422 bad quality, 409 render from another blueprint, full job with a fake engine, file downloads, save to project |
| `tests/test_atmosphere.py` (9, AU-06) | Blueprint atmosphere levels follow era taste and carry a palette and reasons. Every pad / shimmer / choir / sparkle pitch is a tone of the chord sounding at that moment; drones are tonic and fifth. Swells end exactly on the downbeat of a chorus or an energy lift. Setting a section's Atmos to off empties it (bed and swells aside); old blueprints get era defaults. Era palettes differ (neo-soul has no choir; vinyl vs air beds). **Gate (ground truth, two eras):** rendered atmosphere is >85% in-key by chroma, section loudness follows planned energy (Spearman ≥ 0.8 across verse/pre-chorus/chorus/bridge; chorus above verse and pre-chorus), and the sparkle's onsets sit within 25 ms of the eighth-note grid. Mixer `gain_offsets` are opt-in. A render includes the atmosphere stem, its reasons and an Atmosphere MIDI track |
| `tests/test_voice_library.py` (11, Session 009) | A synthetic singer (harmonic tones, vibrato, breaths). A clean take is usable with a 6–20 s sung reference; clipped, noisy, short and quiet takes each explain what to fix. A voice saved from a take has the singer, consent time, spoken-consent clip (not in the dataset), take file, dataset clips and the sung range; a second take grows it; rename. Consent and quality are required. Old profiles still load. History survives a new store instance (input kept, peaks, rating, delete). API: take check → save from take → sample → rename → 422 without consent → conversion (fake provider) lands in history → audio / input / peaks / rating / to-project / delete. **Three simultaneous conversions never run at once** (max concurrency 1) |
| `tests/test_generation.py` (13, AU-05) | Chord tones (6 cases, slash bass). Keys notes are always tones of the sounding chord; no drums where the arrangement has them off; crashes on chorus arrivals. Voice leading moves about a step per voice. The melody guide stays inside each section's register and scale, is deterministic per seed and varies with it. MIDI round trip (tempo, track names, note counts, timing). **Gate (ground truth):** render a 12-bar blueprint, then analyse the audio: tempo within ±3 BPM from the drums stem, the key family (key, relative or fifth-neighbour) from keys + bass, the keys stem's loudest pitch classes are chord tones in ≥90% of chord windows, a mastered stereo WAV of the right length at ≤ −0.9 dBTP, and the melody guide kept out of the stems. Render job → project assets. API: providers, 422 on a bad blueprint, render job, stem and MIDI downloads, 404 for unknown files, save to project |
| `tests/test_artist_dna.py` (13, AU-03) | Version-word stripping. Families group versions but not shared first words. Versions share one song's weight. Switched-off songs ignored. Covers down-weighted. Relative keys share a family. Loop rotations merged. Form and lift. Melody only from vocal stems. Voice headroom/footroom. Every trait has confidence. Empty state. API |
| `tests/test_theory_atlas.py` (22, AU-03B) | Canonical Atlas valid, all 6 eras. Provenance and honest status on every row. Guard rejects melodies/lyrics, absolute chord names, over-long progressions, note sequences in vocal anchors, and 'sourced' rows citing only the placeholder. Roman-numeral parser. **Gate:** 80s R&B returns ≥3 transposable, sourced harmony candidates plus vocal and groove, keys always suggested, no melody keys in the answer. Filters steer results. Keys fit the voice and prefer DNA families; minor keys use the relative-major family; a narrow voice gets an honest stretch answer. API. Export matches the JSON (7 sheets / 7 CSVs) |
| `tests/test_artist_library.py` (26, AU-02 + previews) | Stem-role naming (7 cases). KITS instrumental vs stem. Titles/variants. Scan grouping of loose files, a stem folder, a stems zip and a lone stem. Zip loading leaves no temp files. Rescan keeps analyses and marks changed songs stale. **Analysis never writes to the catalog** (size + mtime snapshot). Removing a folder forgets songs but leaves files. **Ground truth on a synthetic song** (90 BPM, C major, I–V–vi–IV, V-C-V-C with chorus backing vocals): tempo ±3, key, progression, chorus found from backing vocals, melody range, rhythm source, instrumentation. Mix-only structure finds repeats. API flow: add folder → analyse job → song analysis → include toggle |
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
| **Artist DNA** (AU-03) | **Built (AU-03):** `artist/dna.build_dna` over the AU-02 library, `GET /artist/dna`. Feed its `traits.key.families[].major_tonic`, tempo band, loops, form and `traits.voice` into AU-04. Originally planned from: aggregate `artist/analyses/*.json` over songs with `included = true`, weighting stem sets higher (their melody, structure and rhythm come from stems). Also available: `engine/analysis.analyse` for spectral, loudness, stereo and onset features. `engine/loudness.measure` for LUFS/TP. `voice/pitch.detect_key`, `_track_pitch`, `_segment_notes` for key and melody contour. `voice/profiles.analyse_dataset` for vocal range and readiness. Pipeline `session.json` as a model of provenance output | New: tempo/structure/chord/section analysis, catalog storage under `%LOCALAPPDATA%\Auralis\artist\`. The local uncommitted `engine/harmony.py` (scale-degree profiles, out-of-key notes) could become a harmony-trait extractor if the user commits it |
| **Song Blueprint** (AU-04) | **Built (AU-04):** `composer.build_blueprint` over `artist/dna`, `theory.candidates`, `theory.suggest_keys`/`key_fit`, the trained voice range and the library summaries; saved via `ProjectStore.save_blueprint`. AU-05 should read `sections[].chords` (bar, beat, beats, roman, chord), `groove`, `arrangement`, `energy_curve` and `sections[].vocal`. `arrangement.mix_profile` names a `StyleProfile` for AU-10 | `composer/chords.parse_key` accepts G♯/D♭ spellings that `voice/pitch.parse_key` rejects |
| **Composer** (AU-05) | **Built (AU-05):** `composer.arrange` + `composer.midi` + `generation` (provider registry, `synth`) + `engine.pipeline.run` for mix/master | Next: better instruments as extra providers (SoundFont/sampler in an isolated venv), per-section regenerate of a single part |
| **Atmosphere Engine** (AU-06) | **Built (AU-06):** `generation/atmosphere.py` (plan + render), the `atmos` section role, mixed as `other` −6 dB via `mixer` `gain_offsets` | Next: sample-based textures as a provider; per-layer edits beyond the section level |
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
- ~~Artist DNA V1~~, done in AU-03. ~~R&B Atlas data layer~~, done in AU-03B (still to do: curate more rows and validate the `hypothesis` rows against real data; ingest approved corpus statistics).
- ~~Music-library import and analysis~~, done in AU-02. Still missing: lyrics text analysis, chord qualities beyond major/minor triads (7ths, sus), time signatures other than 4/4, and confident section roles for mix-only songs.
- ~~Retrieval, similarity guard~~, done in AU-12 (audio fingerprinting not done).
- ~~Song blueprint~~, done in AU-04. Still missing: lyric writing, per-line syllable fitting, meters other than 4/4, and a prompt reader beyond keywords.
- ~~Composer, MIDI rendering~~, done in AU-05 (the local synth is a sketch-quality provider). ~~Atmosphere~~, done in AU-06. Still missing: sample-based instruments, generative-audio providers (AU-11).
- My Voice redesign: V1–V4 and microphone capture built (Sessions 009, 015). Still planned: V5 (full-song vocal separation; needs a model) and cancelling a queued conversion. See `docs/VOICE_STUDIO_PLAN.md` §7.
- ~~Vocal harmony/doubles generator, full-song voice orchestration~~, done in AU-08/09. Guide singer: V1 (no intelligible words; needs a lyric-capable provider).
- A generic provider interface/registry and a GPU/model scheduler. The audit hit exactly the memory contention this is meant to prevent (see below).
- Diff-MST "Path B" mixer (comment-only placeholder).
- Windows one-file packaging (documented sketch only).

**Defects and drift found (not fixed in AU-00, which is documentation only):**

1. ~~**Host memory blocks live Seed-VC conversion.**~~ Resolved in Session 011 when commit memory allowed (a conversion peaks at about 9 GB of commit). With LM Studio resident, RAM is still the bottleneck: Pitch Polish's full-rate pYIN over a whole song pages heavily. Windows `os error 1455` (paging file too small) happened while loading Whisper weights. Commit charge was 5.6 GB free of a 63.7 GB limit, with LM Studio resident. Free memory or enlarge the page file before voice work.
2. ~~**Seed-VC failure diagnostics can be empty.**~~ Fixed in Session 011 (UTF-8 decoding of the provider output). Through `SeedVCProvider.convert` the same failure surfaced as `Voice conversion failed: Unknown Seed-VC error`, with both stdout and stderr empty. Running the command directly showed the real traceback. Consider logging the full subprocess output to the job dir.
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
