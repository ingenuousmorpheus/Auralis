# My Voice redesign plan: Kits-style voice page in the Auralis console

**Added:** 2026-09-24 (Session 007)
**Status:** PLAN. Nothing in this document is built yet.
**Asked for by the user:** "make the voice creation page similar to kits.ai and have it working in the same gui structure".

The user shared two screenshots: the current Auralis **My Voice Studio** page and the Kits.ai **Convert** page. This plan takes Kits' *workflow layout* and builds it inside the existing Auralis shell (gold console theme, `Sidebar`, `PlayerBar`, page routing in `App.jsx`). It reuses the voice engine that already works (profiles, Studio Voice dataset, paired calibration, Seed-VC training and conversion, Pitch Polish, Vocal Finish).

**Branding.** Auralis copies the *layout ideas*: a voice hero, input beside output, a history of takes and a clone wizard. It uses no Kits name, logo, colours, copy or assets. This follows the same rule as the Suno-style Create redesign (Session 004).

---

## 1. What the two pages do today

| | Auralis My Voice Studio (current) | Kits Convert (reference) |
|---|---|---|
| Layout | One long page with numbered cards: engine status, 1 create profile, 2 build Studio Voice, 3 convert guide, then polish | A voice hero at the top, then **Input** on the left and **Output** on the right, with sub-pages in the sidebar |
| Voice selection | A dropdown inside card 2 | A big voice tile plus *Switch voice* and *Add voice* buttons |
| Input | One guide file | *Audio input* (drop up to 5 files) or *Song input* (a full song; the vocal is split out first) |
| Output | Only the latest result, with A/B players | A persistent list of every conversion: waveform, play, download, menu, "how did that sound?" |
| Cloning | Cards 1 and 2 mixed into the convert page | A separate *Clone Voices* area |
| Extras | Pitch polish, auto polish, Vocal Finish rack (elsewhere) | Harmonies, history, tools |

Engine features Auralis already has, and Kits does not show locally: trained Studio Voice checkpoints, paired calibration, readiness scoring, Pitch Polish, and Vocal Finish with instrumental-aware placement. The redesign must keep all of them.

## 2. Target layout (inside the existing shell)

The sidebar stays as it is. **My Voice** opens a page with four tabs, the same way Create uses a Simple/Advanced segment:

```text
┌ My Voice ───────────────────────────────────────────────────────────────┐
│ ┌──────────┐  MY STUDIO VOICE                 [Switch voice] [+ Add voice]│
│ │  voice   │  Studio trained · D3–C5 · readiness 72% · 1 paired take     │
│ │  tile    │  Engine: Seed-VC ready (GPU)                                 │
│ └──────────┘                                                             │
│  [ Convert ]  [ Clone a voice ]  [ Harmonies · soon ]  [ History ]        │
├───────────────────────────────┬──────────────────────────────────────────┤
│ INPUT                         │ OUTPUT                                   │
│  Audio input | From My Music  │  guide_take_2.wav → My Studio…  2 min ago │
│  ┌─────────────────────────┐  │  ▶ ▁▃▅▇▅▃▁▃▅▇▅▃▁  ⤓  ⋯   A/B  Save  👍 👎 │
│  │ Drop up to 5 dry vocals │  │  guide_take_1.wav → My Studio…  5 min ago │
│  └─────────────────────────┘  │  ▶ ▁▃▅▇▅▃▁▃▅▇▅▃▁  ⤓  ⋯   A/B  Save  👍 👎 │
│  Quality  fast · studio · ultra│  (queued) chorus_double.wav   waiting…  │
│  Pitch shift  −12 … +12        │                                          │
│  After conversion: ○ none      │                                          │
│    ● auto polish ○ pitch only  │                                          │
│  Instrumental (optional) [+]   │                                          │
│  [ Convert 3 files ]           │                                          │
└───────────────────────────────┴──────────────────────────────────────────┘
```

- **Voice hero.** A generated cover tile (same `Cover` helper as My Music), the profile name, its kind (instant / dataset / studio trained), the trained range, readiness, paired takes and engine status. *Switch voice* opens a drawer that lists every profile with its status. *Add voice* opens the Clone tab.
- **Convert tab.**
  - *Audio input:* drop up to 5 dry vocals. They join a **queue** and convert **one at a time**: host memory is tight and Seed-VC must never run twice at once (see §5).
  - *From My Music* replaces Kits' "Song input". Auralis cannot split a full mix into stems locally yet, but stem sets in My Music already have a lead-vocal stem. Pick a song and its `lead_vocal` stem becomes the guide. Full-mix separation is a later provider (§4, V5).
  - Settings map onto what `/voice/convert` already takes: quality `fast|studio|ultra` and `semitone_shift` −12…+12. The after-conversion choice maps onto `/voice/auto-polish` (pitch then finish) or `/voice/pitch` alone. The optional instrumental feeds Vocal Finish placement and Pitch Polish key detection.
- **Output list (History).** Every conversion is kept across restarts. Each row has a waveform, play (through the shared `PlayerBar`), download, A/B against the input, *Save to project* (the existing `SaveToProject`), *Send to Vocal chain*, and 👍/👎 with an optional note. The ratings help decide which takes become paired-calibration material.
- **Clone a voice tab.** The existing steps become a clear wizard with the same endpoints:
  1. Reference plus consent (`POST /voice/profiles`). Consent stays mandatory.
  2. Studio Voice dataset: upload takes, see the readiness meter and coverage (`POST /voice/profiles/{id}/recordings`).
  3. Paired calibration, optional (`POST /voice/profiles/{id}/paired-calibration`).
  4. Train with progress (`POST /voice/train`, one at a time).
- **Harmonies tab.** Shown as "coming with AU-09" (roadmap §10). It is not faked.
- The engine install/status card moves into the hero as a status line. The install action stays available when Seed-VC is missing.

## 3. Backend work needed

Most of the engine exists. The gaps are persistence and queuing.

| Need | Today | Change |
|---|---|---|
| Conversion history that survives a restart | Results live in the in-memory `JOBS` dict and `%TEMP%` | New `auralis/voice/history.py`: a `VoiceHistoryStore` at `%LOCALAPPDATA%\Auralis\voices\<profile_id>\history\` with `index.json`. Each finished conversion (and its polish outputs) is copied in with its input name, settings, time, duration and rating. Modeled on `ProjectStore` (copy, never move) |
| Queue of up to 5 files | One job per request, each starting a Seed-VC subprocess immediately | A single worker queue in the API (`asyncio.Queue` plus one consumer), so conversions never overlap. Queued jobs report `stage="queued"` with their position |
| Waveforms | None | `GET /voice/history/{id}/peaks`: about 600 min/max pairs computed once with soundfile and cached as JSON beside the take. No client-side decoding of large WAVs |
| Guide from a My Music stem | Not possible | `POST /voice/convert` accepts `song_id` + `stem_role` instead of a file. The stem is read through `LibraryStore`/`SongAudio` into the job folder; the catalog is read only |
| Ratings and notes | None | `PATCH /voice/history/{id}` with `{rating, note}` |
| Clear errors | Seed-VC failures can surface as "Unknown Seed-VC error" (architecture gap 2) | Save the subprocess stdout/stderr to the job folder, and show the last lines plus a plain explanation for `os error 1455` (paging file too small: close large apps or enlarge the page file) |

New endpoints: `GET /voice/history?profile_id=`, `GET /voice/history/{id}/audio|input|peaks`, `PATCH/DELETE /voice/history/{id}`, `GET /voice/queue`. Existing endpoints stay unchanged, so the Vocal chain rack and Projects keep working.

## 4. Build phases and gates

| Phase | Scope | Gate |
|---|---|---|
| **V1 Layout** | New `VoicePage.jsx` shell: hero, tabs, Convert input/output split, Clone wizard reusing the current `VoiceStudio.jsx` logic. The old component stays until V1 passes | Every current voice action (create profile, dataset, paired take, train, convert, pitch, auto polish) works from the new page, with no console errors at 1440 px and 375 px |
| **V2 History** | `VoiceHistoryStore`, history endpoints, output list with waveforms, A/B, download, save to project, ratings | A conversion made before a backend restart is still listed, playable and downloadable after it |
| **V3 Queue** | Single-worker conversion queue, 5-file drop, per-item progress, cancel queued items | Five dropped files convert one after another. Only one Seed-VC process exists at any time (checked with the process list) |
| **V4 From My Music** | Pick a stem-set song and use its lead-vocal stem as the guide | A catalog lead-vocal stem converts without writing anything into the catalog folder (snapshot test, as in AU-02) |
| **V5 Song input** | Optional local vocal-separation provider (isolated venv like Seed-VC) so a full mix can be a guide | A full mix gives a separated vocal that converts. The provider is optional and Auralis works without it |

V1–V3 give the Kits-style experience. V4 is an Auralis-only advantage (the user's own stems). V5 needs a new provider and is gated on host memory, as noted below.

## 5. Constraints carried forward

- **Local only.** No uploads, no paid APIs. Voice files, datasets and checkpoints stay in `%LOCALAPPDATA%\Auralis\voices\` and never enter Git.
- **Host memory.** Live conversion is still unverified on this host (`os error 1455`, Session 001). The queue in V3 exists so Auralis never stacks Seed-VC runs. V1 and V2 can be built and tested with the provider mocked; the live check happens when commit memory allows.
- **Consent.** Profile creation keeps its consent checkbox. The Clone wizard states it on the first step.
- **Do not rebuild the engine.** `SeedVCProvider`, `pitch_polish`, `finish_vocal`, `ingest_paired_calibration` and training are reused exactly as they are.
- **Tests.** Store and API tests like `tests/test_projects.py`: history survives a new store instance, the queue never runs two jobs at once (provider mocked), and catalog stems are read only.

## 6. Open questions for the user

1. Should *History* be per voice (Kits-style) or one list across all voices with a filter? The plan assumes per voice with an "all voices" filter.
2. Should 👍 takes be offered as paired-calibration candidates automatically, or only suggested?
3. Is V5 (full-mix separation) wanted soon, or is *From My Music* stems enough for now?
