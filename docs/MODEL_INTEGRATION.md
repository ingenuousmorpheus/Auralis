# Plugging in a new engine (ACE-Step, DiffSinger, or another model)

**Added:** 2026-09-25 (Session 017). The Auralis side is done and tested. What remains is installing a provider, which needs the user's go-ahead (large downloads, licences: see `docs/MODEL_OPTIONS.md`).

## The pipeline and its seams

```text
composition (blueprint)                        auralis/composer/*
   │
   ├─► instrumental: InstrumentalRenderer      generation.PROVIDERS["synth"]
   │      └─ sections marked `renderer: <id>`  → SectionGenerator   (ACE-Step goes here)
   │
   ├─► guide vocal:  GuideSinger               REGISTRY.guide_singer()   (vocalise → DiffSinger)
   ├─► My Voice:     VoiceConverter            REGISTRY.voice_converter() (Seed-VC)
   ├─► pitch polish / vocal finish             voice/pitch.py, voice/finish.py (unchanged)
   └─► stems → mix / master                    engine/pipeline.py (unchanged)
```

Every heavy engine runs inside `auralis.models.MODELS.use(model_id)`:
- **One heavy model at a time.** Jobs never overlap, and use is re-entrant within one thread.
- **Memory check before loading.** A shortage gives a plain error, not a mid-job `os error 1455`.
- **Other resident models are unloaded first.**
- **Release after the job,** by policy:
  - `balanced` (default): unload straight away.
  - `keep_warm`: keep the model until another needs the slot, or until it has been idle `idle_seconds`.
  - `low_memory`: like balanced, but requires the model's full memory estimate.

The user controls this in Studio → Advanced: engines and GPU (API: `GET /models`, `POST /models/policy`, `POST /models/select`, `POST /models/release`). Create never shows it.

## The interfaces (`auralis/models/interfaces.py`)

| Kind | Class | Must implement | Returns |
|---|---|---|---|
| `section_generator` | `SectionGenerator` | `generate(SectionRequest)` | `SectionResult(paths={"mix": wav, ...}, sample_rate, seconds, provider)` |
| `guide_singer` | `GuideSinger` | `sing(score, total_seconds, seed)`; `sings_words`; `languages` | dry mono float32 at 44.1 kHz |
| `voice_converter` | `VoiceConverter` | `convert(ConversionRequest)` | dict with `output_path` and provenance |

All of them are `ManagedModel`s with a `spec: ModelSpec` (id, kind, licence, `heavy`, `resident`, `vram_gb`, `commit_gb`, `min_commit_gb`) and `is_installed()`, `is_loaded()`, `load()`, `unload()`.

`section_prompt(blueprint, section)` builds a plain-language prompt from the blueprint only: era, section, BPM, key, energy, chords and the non-vocal arrangement, ending "Instrumental, no vocals.".

## Resident workers (`auralis/models/worker.py`)

A heavy model lives in its own venv and process: `%LOCALAPPDATA%\Auralis\providers\<name>\` with `.venv\Scripts\python.exe` and `auralis_worker.py`. This keeps dependencies and licences out of the MIT package, like Seed-VC.

The protocol is JSON lines:
- **Start (`load`):** the worker loads its weights, then prints `{"ready": true, ...}`. Non-JSON progress text is ignored.
- **Request:** Auralis writes `{"id": n, "op": "...", ...}`. The worker answers `{"id": n, "ok": true, ...}` or `{"id": n, "ok": false, "error": "..."}`. Audio travels as file paths, never through the pipe.
- **Stop (`unload`):** Auralis sends `{"op": "shutdown"}`. If the worker hasn't exited within the grace period, it is killed. RAM and VRAM go back with the process.

The worker's stderr goes to a log file (an unread pipe would stall it), and its tail is shown when something fails.

## ACE-Step (section generator)

The adapter `auralis/models/builtin.py::ACEStepSections` is written and registered. It reports *not installed*.

To install (only with the user's go-ahead):
1. Create `%LOCALAPPDATA%\Auralis\providers\ace-step\` with its own `.venv` holding ACE-Step and its weights (Apache-2.0).
2. Add `auralis_worker.py` there. It loads the pipeline, prints `{"ready": true}`, and answers `generate_section` with `prompt, seconds, tempo, key, seed, out_dir, stems`, writing `<out_dir>/<name>.wav` and replying `{"ok": true, "paths": {"mix": "..."}, "sample_rate": 44100}`.
   - Its output must be exactly `seconds` long (trim or pad) so it lines up with the section.
   - Its prompt already says "Instrumental, no vocals"; vocals always come from the user's voice path.
3. In Studio → Engines choose ACE-Step for *Generated sections*. In the blueprint, a "Render with" choice then appears on each section card; sections set to ACE-Step render through it into a `generated` stem (mixed as harmonic). Everything else stays with the synth.
4. **Memory:** its spec asks for about 12 GB free commit (roughly 8–12 GB VRAM). The manager unloads anything resident before loading it and, under `balanced`, frees it right after. Seed-VC and ACE-Step can never be loaded together.

**Test seam already in place:** `tests/test_models.py::test_render_uses_a_section_generator_for_marked_sections_only` (a fake generator), plus `test_planned_providers_plug_into_the_worker_lifecycle` (a stand-in worker in the ACE-Step folder).

## DiffSinger (guide singer with words)

The adapter `DiffSingerGuide` is written and registered. It reports *not installed*.

To install (only with the user's go-ahead):
1. Create `providers\diffsinger\` with its own `.venv`, DiffSinger (Apache-2.0) and an English voicebank **whose licence allows the intended use**. The free English voicebanks found are non-commercial; a commercial licence has to be bought, and that is the user's decision.
2. Add `auralis_worker.py`. It answers `sing` with `notes` (`GuideNote.to_dict()`: start, duration, midi, velocity, syllable, vowel, onset, phrase_end), `seconds`, `seed` and `out_path`, writing a dry WAV. Syllables come from `voice/guide.py`; a real engine will want phonemes (ARPAbet), and that conversion belongs in the worker.
3. Choose it in Studio → Engines → *Guide singer*. `sing_song` then uses it for the lead and every backing part, inside the model manager: the singer is loaded, it sings, and it is unloaded before Seed-VC converts.
4. `guide_sings_words` in the song result becomes true, and the UI's "doesn't pronounce clear words yet" note can key off it.

## Seed-VC (voice converter, working now)

`SeedVCConverter` wraps the existing `SeedVCProvider` unchanged. It is not resident, because `inference.py` runs once per call and frees its own memory, so it only takes the slot and the memory check: about 6 GB minimum free commit, 9 GB typical. The API points it at the shared provider (`main.VOICE_PROVIDER`).

`api/voices.convert_with_voice` is the single entry for `/voice/convert`, Sing and Make the whole song. The old `ENGINE_LOCK` is gone; the model manager's slot replaces it with the same one-at-a-time guarantee, which is still tested.

## Not done yet, deliberately

- No engine is downloaded or installed.
- No vocal-separation provider (V5): Demucs weights are non-commercial, see `MODEL_OPTIONS.md`. It would be a new kind (`separator`) with the same pattern.
- VRAM is not measured live. The memory gate uses system commit memory, which is what failed on this host. A GPU query (for example `nvidia-smi`) could be added to `status()` later.
