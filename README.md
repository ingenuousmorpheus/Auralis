<div align="center">
<img width="200" height="200" alt="Auralis logo" src="docs/logo.svg" />

# Auralis

**Local-first mixing, mastering & voice studio.** Your audio never leaves your machine.
</div>

Auralis mixes supplied stems or masters a finished stereo mix, matches it to a
chosen *sound*, hits a loudness target, and enforces a safe true-peak ceiling —
entirely offline. Version 0.5 adds a private, trainable singing voice studio alongside the
stem-mixing path, audible style targets, stereo-safe processing, and
reproducible mix reports.

Audio-to-MIDI instrument reconstruction is not implemented yet. Its technical
plan is documented in
[`docs/RECONSTRUCTION_ROADMAP.md`](docs/RECONSTRUCTION_ROADMAP.md).

> **On "AI":** almost all of Auralis is deterministic DSP, not a language model.
> A GGUF / LM Studio is **not** used to process audio. The only place a local LLM
> belongs is the optional natural-language control layer described in the design
> doc (§5A). Don't load a GGUF expecting it to master a track.

---

## What Auralis 0.5 does

- Upload a stereo mix (WAV / FLAC / MP3).
- Pick a **sound** — five measurable profiles (Maximalist Pop Polish,
  Vocal-Forward R&B, Rhythmic Sparse Low-End, Warm Soul, Neutral Transparent).
  Profiles are named for the sound with an `inspired_by` note; they do not
  impersonate any individual.
- **Match a reference track (Ozone-style).** Optionally point Auralis at a song
  you like — your own copy, on your machine. Matchering *analyses* its frequency
  response, RMS, peak and stereo width and retunes your track toward it. The
  reference's audio is never copied into the output and never stored in the repo;
  it lives only in the job's temp folder and is discarded after. This mirrors how
  iZotope Ozone's Master Assistant uses a reference.
- Master to a loudness target with a true-peak ceiling (default −1.0 dBTP).
- Download a 24-bit WAV.
- Mix multiple stems with filename-assisted role detection, manual overrides,
  masking-aware EQ, role balancing, panning, and per-role dynamics.
- Preserve stereo stems through processing and resample mixed-rate sessions
  with polyphase filtering.
- Export a human-readable mix report and complete session JSON.
- Create a consent-confirmed local voice profile from a clean singing reference
  and convert dry guide vocals with the optional GPU-isolated Seed-VC provider.
- Build a full Studio Voice from 10–45+ minutes of recordings, measure vocal
  range and dataset coverage, resume GPU fine-tuning, and automatically use the
  trained checkpoint during conversion.
- Run an analysis-driven Vocal Finish after conversion, including adaptive EQ,
  de-essing, serial compression, harmonic density, stereo depth, instrumental
  placement, before/after auditioning, and an editable decision report.
- Use One-Click Studio Polish to detect key and melody, preserve vocal
  expression while correcting note centers, and feed the tuned vocal directly
  into Vocal Finish.
- Add verified guide/real-vocal pairs through Paired Calibration, with automatic
  mismatch rejection and phrase-level alignment for training and evaluation.

The mastering stage uses [Matchering](https://github.com/sergree/matchering) when
a reference is supplied (either by you at runtime, or — if you legally curate one
— bundled with a profile), and a transparent internal-target chain otherwise.

---

## Run it (dev)

Two processes: the Python backend and the Vite frontend.

### Windows one-click launcher

Double-click `Run Auralis.bat` in the project folder. It starts both services,
waits for them to become healthy, and opens the interface. Double-click
`Stop Auralis.bat` when finished.

### 1. Backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
python -m uvicorn auralis.api.main:app --app-dir E:\Auralis --host 127.0.0.1 --port 8001
# serves the API at http://127.0.0.1:8001
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # opens http://127.0.0.1:5173 and uses API http://127.0.0.1:8001
```

Open `http://127.0.0.1:5173`, drop in a mix, pick a sound, master, download.

### Tests

```bash
pip install -e ".[dev]"
pytest -q
```

---

## Models & first run

Model weights are **not** stored in this repo (they're multi-gigabyte and
third-party). They're fetched to a local, git-ignored `checkpoints/` cache — so a
fresh clone is small.

- **Mixing & mastering** — no model downloads required. Works out of the box.
- **Voice studio (optional)** — the singing-voice conversion path uses the
  optional GPU-isolated **Seed-VC** provider. Install it once with:

  ```powershell
  ./tools/install_seed_vc.ps1
  ```

  On first use, the voice pipeline downloads its model weights from Hugging Face
  (Whisper, BigVGAN, CAMPPlus, RMVPE, Seed-VC — several GB total) into
  `checkpoints/`. This is a one-time download; subsequent runs are offline.

Nothing you process — your mixes, references, or voice recordings — is ever
uploaded. Only the initial model weights are downloaded, and only for the
optional voice features.

---

## Project layout

```
auralis/
├── auralis/
│   ├── engine/          # pure DSP — usable as a standalone library
│   │   ├── loudness.py      # LUFS measure / normalize, true-peak ceiling
│   │   ├── mastering.py     # Matchering + internal-target fallback
│   │   ├── profiles_loader.py
│   │   └── profiles/        # the five "sound" YAML profiles
│   ├── api/             # FastAPI app (127.0.0.1 only)
│   ├── packaging/       # Windows build notes (Phase 4)
│   └── run.py           # `auralis` entry point
├── frontend/            # React + Vite GUI
├── tests/               # engine + golden-target tests
└── docs/DESIGN.md       # full technical design document
```

The `engine` package has **no dependency** on the API or frontend.

---

## Push this to your own GitHub

This repo was scaffolded locally. To put it on GitHub from your work computer:

**Option A — drag-and-drop (no git needed):**
1. On github.com, create a new **private** repo named `auralis` (leave it empty —
   no README/license, this repo has them).
2. Open the repo, click **uploading an existing file**, and drag the whole
   unzipped folder's contents in. Commit.

**Option B — git CLI:**
```bash
cd auralis
git init
git add .
git commit -m "Auralis 0.3: stereo-safe stem mixing and mastering"
git branch -M main
git remote add origin https://github.com/<your-username>/auralis.git
git push -u origin main
```

Start **private** — you can flip it public once it's where you want it.

---

## License

MIT. See [`LICENSE`](LICENSE).

Built on open-source DSP: Matchering, pyloudnorm, soundfile, FastAPI.
