# Auralis Session

> Canonical lightweight continuity checkpoint for ChatGPT, Claude, Codex, and
> future Auralis work.
>
> Last reconciled from GitHub: 2026-10-06.
> Repository: ingenuousmorpheus/Auralis
>
> Read this before proposing a new Auralis phase. Code and tests establish what
> exists; the owner's explicit decisions establish product direction.

## Product identity

Auralis is a local-first music, mixing, mastering, composition, and personal
voice studio. Its strongest product direction is not "another Suno clone" and
not "another DAW." It should feel like a premium creative instrument built
around the user's own music and voice.

Core product message:

> YOUR VOICE. YOUR MUSIC. YOUR STUDIO. LOCAL FIRST.

The owner wants a luxury-feeling public product while preserving local
processing and user control.

## Current product priorities

1. Personal voice is a flagship feature, not a side utility.
2. My Voice should make a trained personal voice feel like a reusable musical
   instrument.
3. The user's trained voice should be the natural/default voice choice where
   the workflow needs a singer, while still allowing other saved voices.
4. Auralis should combine a Kits-like clarity around voice workflows with a
   Suno-like creative flow, without copying either product's branding,
   distinctive UI, assets, or wording.
5. Existing local music-production capability should remain available beneath
   a simpler luxury interface.
6. The project should remain extensible so users can eventually bring their own
   legally installed audio tools/providers.

## Verified current state

Recent committed milestones include:

- My Voice microphone capture and Kits-inspired workflow.
- Persistent voice conversion history and one-at-a-time conversion queue.
- My Music lead-vocal stem -> saved voice conversion.
- Studio Voice training and trained-checkpoint conversion.
- AU-05 structured composer and local instrumental rendering.
- AU-06 atmosphere engine.
- AU-07/08 guide singer + full-song voice pipeline, verified live.
- AU-09 vocal production: doubles, harmonies, ad-libs as separate stems.
- AU-10 full song assembly with persistent project stems.
- AU-12 Artist DNA retrieval and similarity guard.
- AU-13 demo-to-song.
- Model lifecycle/registry with one-heavy-engine-at-a-time policy.
- Seed-VC as the working voice converter.
- ACE-Step and DiffSinger adapters/provider seams present but not installed.
- Harmonic Reference committed as a note-domain analysis/advice tool.
- Public artist integration plan committed.
- Luxury My Voice UI first pass committed on 2026-10-04.

Latest reviewed implementation commits at this checkpoint:
- `1620c13` — My Voice persists a deterministic personal-voice fallback (explicit saved choice > trained Studio Voice > Studio dataset > first available voice).
- `aad4c9e` — Create now reads that same remembered selection and sends it as `profile_id` to the existing full-song pipeline, so the voice selected in My Voice is the voice used for new vocal renders. Fallback precedence is identical and is persisted when the remembered id is stale.

## Luxury UI state

Owner-approved direction lives in:

`docs/AURALIS_LUXURY_UI_DESIGN.md`

The first My Voice implementation now exists:

- `frontend/src/Lux.jsx`
- `frontend/src/lux.css`
- redesigned `VoicePage`
- selected-voice hero
- input/output workbench
- waveform players
- conversion result cards
- My Music input
- voice/training status
- tool cards
- GPU/model status

The implementation commit reports successful Vite build, 29 relevant tests,
responsive checks, and stubbed queue verification.

Important: the first pass is still awaiting owner visual acceptance. Do not
spread the visual system across every page until the owner has evaluated the
My Voice screen and requested/accepted adjustments.

## Voice direction

The personal voice-copying workflow is one of Auralis's strongest
differentiators.

Current architecture already supports:

- consent-confirmed voice creation;
- microphone capture;
- instant/reference voices;
- dataset growth;
- range/readiness measurement;
- Studio Voice training;
- trained checkpoint use;
- conversion history;
- conversion from My Music lead-vocal stems;
- full-song singing pipeline;
- pitch polish;
- Vocal Finish;
- vocal doubles/harmonies/ad-libs.

Do not rebuild this as a second voice subsystem.

### Default personal voice intent

Product intent: when an owner/user has a ready trained personal voice, Auralis
should prefer/present that voice as the natural default for creation rather than
making the user repeatedly hunt for it.

This is a UX/product preference, not permission to silently train, overwrite,
share, upload, or publish a voice.

A future implementation should define deterministic selection rules, for
example: explicit project choice > explicit user default > ready personal
Studio Voice > existing safe fallback. Do not implement that precedence until
the existing voice-selection paths are audited so old projects remain
reproducible.

## Model/provider state

Auralis already has the correct seam for heavyweight providers:

- `auralis/models/lifecycle.py`
- `auralis/models/interfaces.py`
- `auralis/models/registry.py`
- isolated worker/provider environments
- one heavy model at a time
- commit-memory gate
- advisory VRAM reporting

ACE-Step is planned as a section generator and has an adapter, but is not
installed. DiffSinger has a guide-singer adapter, but a suitable voicebank
licence remains a gating concern.

Do not download/install a large model merely because its adapter exists.

Re-check upstream licences before any provider installation or public release.

## Harmonic Reference

Harmonic Reference is BUILT and committed.

It compares a target and reference in scale-degree/note space and reports:

- transposition;
- mode differences;
- scale-degree balance;
- out-of-key notes with timecodes;
- register differences;
- confidence.

It advises only. Pitch Polish remains the stage that changes audio.

Do not merge Harmonic Reference conceptually with the AU-09 vocal harmony
generator; they solve different problems.

## VST / existing-plugin integration direction

Owner direction: investigate letting Auralis use audio plug-ins the user already
owns, including examples such as Waves, Soundtoys, and Antares, as optional
skills/tools in the local production chain.

This is a future integration track, not an implemented capability.

Design goal:

Auralis decides *what processing is needed* -> an approved local plug-in host
executes the user's installed plug-in -> Auralis measures/compares the result
and continues the pipeline.

Guardrails:

- Do not bundle or redistribute commercial plug-ins.
- Do not bypass licence managers, copy protection, activation, or vendor terms.
- Do not assume a plug-in is installed or licensed.
- Do not hard-code one vendor as required.
- Keep Auralis functional without commercial VSTs.
- Prefer a provider/adapter boundary rather than putting vendor-specific logic
  throughout the DSP engine.
- Preserve reproducibility by recording plug-in identity/version and parameter
  state when possible.
- A failed/unavailable plug-in should fall back safely rather than corrupt a
  project.
- Audit VST3 hosting/licensing/automation feasibility before implementation.

A useful future architecture is a `processor`/effect-provider interface beside
the existing model-provider interfaces, with a local host process isolated from
the core engine. That is a proposal, not yet an approved implementation.

## Public artist integration

A public artist integration plan was committed in `334d553`.

Intent: Auralis can be discoverable from the owner's artist/GitHub presence
without turning private/local processing into a cloud dependency.

Preserve the distinction between:

- public presentation/download/discovery;
- local Auralis processing;
- private personal voice assets.

Do not publish personal voice checkpoints or private audio as part of artist
site integration.

## Monetization direction requiring later product decision

The owner has discussed a roughly $10/month public plan and a possible
voice-based ownership/revenue concept. These are product ideas, not finalized
billing/legal terms.

Do not encode a 7% ownership/revenue rule, subscription entitlement, or legal
claim into code until the owner explicitly approves the final model and the
licensing/business implications have been reviewed.

Local/free functionality and paid/public-service functionality should remain
architecturally distinguishable.

## Documentation drift found 2026-10-06

`docs/AURALIS_CURRENT_ARCHITECTURE.md` says its last update was Session 017,
while later committed work includes Harmonic Reference, the public artist plan,
Sessions 018/020, and the luxury My Voice implementation.

That architecture document also references `auralissession.md`, but that file
was not present on GitHub main during this reconciliation.

The README is substantially more current than the architecture header, but it
does not capture all owner product decisions above.

Do not treat the stale architecture header as evidence that later committed
features do not exist.

## Next safe work

When Claude/Codex capacity is available:

1. Owner visually tests the Session 020 My Voice luxury redesign.
2. Fix only issues found in that acceptance pass before propagating the visual
   language.
3. Reconcile `docs/AURALIS_CURRENT_ARCHITECTURE.md` through the latest
   committed feature state.
4. Audit all current voice-selection entry points and propose the safest
   personal-voice default precedence without changing old project behavior.
5. Decide whether ACE-Step installation is worth its local RAM/VRAM cost before
   downloading anything.
6. Research a vendor-neutral local VST3/effect-host boundary before touching
   Waves/Soundtoys/Antares integration.
7. Keep the public artist integration thin: discovery/presentation outside,
   audio and voice processing local.
8. Revisit pricing/ownership terms separately from engineering.

## Handoff instructions

At the beginning of a future Auralis engineering session:

1. Read this file.
2. Read `README.md`.
3. Read `docs/AURALIS_CURRENT_ARCHITECTURE.md`, but account for its documented
   stale sections.
4. Read `docs/AURALIS_LUXURY_UI_DESIGN.md`.
5. Read `docs/VOICE_STUDIO_PLAN.md`, `docs/MODEL_INTEGRATION.md`,
   `docs/MODEL_OPTIONS.md`, and `docs/HARMONIC_REFERENCE.md` when relevant.
6. Inspect commits newer than the latest reviewed commit recorded here.
7. Do not create a parallel voice, model, project, or DSP architecture when an
   existing seam already solves the problem.
8. Preserve local-first behavior and existing project compatibility.
9. Separate owner-approved direction from speculative future ideas.
10. Update this checkpoint after meaningful accepted work.

## This reconciliation

Documentation/continuity only. No audio engine, model, voice data, frontend,
provider, project data, or user audio was modified.


## Session 021 — architecture reconciliation

**Date:** 2026-10-06  
**Scope:** safe continuation while the Session 020 My Voice visual acceptance gate remains open.

Completed:
- Reconciled `docs/AURALIS_CURRENT_ARCHITECTURE.md` through the committed Harmonic Reference, luxury My Voice, deterministic personal-voice selection, and Create/full-song voice-selection work.
- Corrected continuity authority in the architecture document: `AURALIS_SESSION.md` is canonical; older references to missing `auralissession.md` are drift.
- Preserved the owner visual gate: the luxury design is not propagated across all pages until My Voice is visually accepted or corrected.

No runtime/audio/model/frontend behavior changed in this phase, so no runtime test claim is made. The next implementation phase remains the owner-gated luxury shell/navigation propagation; independent non-visual engineering may continue without bypassing that gate.


## Session 022 — luxury shell convergence

**Date:** 2026-10-06  
**Scope:** propagate the approved luxury language to the shared application shell without changing page workflows or backend behavior.

Owner continuation signal:
- After Session 021 explicitly surfaced the visual propagation gate, the owner instructed Auralis work to continue. This phase therefore proceeds with the smallest reversible shared-shell step; full page-by-page visual acceptance is still separate.

Completed:
- Re-skinned the existing sidebar/navigation and global player using the existing Lux design tokens rather than creating a second theme system.
- Replaced the old bridge-console gold emphasis in the shell with the approved obsidian/plum/violet/magenta/cyan "recording studio at midnight" language.
- Preserved all existing navigation ids, routes, player behavior, voice-card behavior and responsive shell structure.
- Changed the static shell status copy from `LOCAL CORE · ONLINE` to `LOCAL · PRIVATE` so the interface does not imply a live health check it does not actually perform.
- Added reduced-motion-safe treatment for the shell logo path.

Files changed:
- `frontend/src/theme.css`
- `frontend/src/Shell.jsx`

Behavioral impact:
- Presentation only. No API, model, DSP, project, voice, storage or audio-pipeline behavior changed.
- No fake controls or unsupported backend capability were added.

Verification status:
- Source-level review completed in-repo.
- This environment did not execute the Vite build or browser visual check, so Session 022 remains pending owner/browser validation before treating the shell appearance as visually accepted.

Next bounded phase:
- Apply the same reusable Lux primitives to the Create page without altering Create's composition, voice-selection, rendering, or project behavior; then checkpoint before moving to My Music/Projects.


## Session 023 — luxury shell: made revertible, completed, verified

**Date:** 2026-10-13
**Scope:** the owner approved the obsidian / violet-plum / cyan-waveform / magenta direction from the Session 020 My Voice pass, and asked for the gold sidebar, wordmark and player bar to match it, *with the original implementation preserved so it can be reverted*. Build, test, screenshot, then stop for review.

Starting state:
- Local `main` was 10 commits behind GitHub (Sessions 021/022 and the voice-selection commits by another agent). Fast-forwarded to `e3c970e`; the local tree was clean.
- Session 022 had already re-skinned the shell by appending unconditional overrides to `theme.css`, unverified: no build or browser check. Those overrides also restyled `.au-btn` on every page.

Changed:
- **Revertible shell.** Session 022's rules moved out of `theme.css` into `frontend/src/shell-lux.css`, each scoped to `[data-shell="lux"]`. `theme.css` is byte-for-byte the original gold shell again (as of `3c5f236`).
  - `App.jsx` sets `<html data-shell>`. The default is `lux`.
  - `?shell=classic` or `?shell=lux` switches and is remembered (`localStorage auralis.shell`).
  - `VITE_SHELL=classic` changes the build default.
- **Missing pieces Session 022 left gold:**
  - the logo's click morph glowed gold: new `lx-morph` keyframes; `Shell.jsx` now resets on any `*-morph` animation end
  - the now-playing cover was a gold icon on brown and the volume slider was ivory (both inline-styled): now violet
  - the console scanline overlay is hidden in the luxury shell
- **Narrow windows (below 900 px), luxury shell only.** These are pre-existing flaws, so classic is untouched:
  - The player's volume row is inline `display:flex`, which beat `theme.css`'s `display:none`, so it spilled below the player. It is now hidden.
  - Two-word nav labels wrapped onto two lines (the top bar was 95 px tall); they now stay on one line (63 px).
- `App.jsx` now imports `lux.css` itself, so the `--lx-*` tokens no longer depend on My Voice being loaded.

Verification (real app, launcher-started backend + Vite):
- `npm run build` clean.
- `test_voice_library` + `test_models`: 29 passed. No backend change.
- **Playwright (system Chrome):** every page at 1440x900, 1280x800, 1024x768 and 820x1000 in the luxury shell; Create and My Voice at 1440 in the classic shell; full-length My Voice captures. 47 screenshots in local `screenshots/session-023/` (git-excluded: My Music shows catalog titles).
  - No horizontal overflow on any page at any size.
  - The only console error is `/favicon.ico` 404. It predates this work: the app has no favicon.
- **Functional checks:**
  - a My Music cover plays in the player (Pause shown, 5.8 s in, violet cover) and pauses
  - the logo morph runs and clears, and still goes to Create
  - `?shell=classic` survives a plain reload (ivory play button) and `?shell=lux` switches back
  - nav reaches all ten pages

Findings and contradictions:
- Session 021 says `auralissession.md` "was not present on GitHub main". It is tracked there (both session files are on `origin/main`). The canonical header also misspelled the repository as `ingeniousmorpheus`; corrected above. `auralissession.md` remains the detailed engineering log (AU-00 to Session 020); this file is the lightweight canonical checkpoint.
- The page bodies are not yet converted. Create, My Music, Artist DNA, Studio, Projects and the tool screens still use gold headings, icons, toggles and corner brackets inside the violet shell. In the luxury shell, gold `.au-btn` buttons already render violet (Session 022's choice, kept). That mix is expected until each page migrates.
- The sidebar voice card still picks "trained or first" voice itself, while My Voice and Create share the remembered selection (`1620c13`/`aad4c9e`). With one voice they agree; with several they can differ. Not changed here (behaviour, not shell look).

Revert:
- Per user: open `http://localhost:5173/?shell=classic`.
- Per build: `VITE_SHELL=classic`.
- In code: delete the `shell-lux.css` import in `App.jsx`. `theme.css` needs no edit.
- In git: the original gold shell is unchanged at `3c5f236`.

Remaining work:
- Owner visual review of the shell (these screenshots and the live app).
- Page-by-page migration to Lux primitives (design section 13): Create first, then My Music / Projects, then Studio and the tool screens, then Release / Export.
- Small items: a favicon (from `docs/icon.png`); the sidebar voice card should use the shared voice selection; the status strip's "Engine details" wraps to its own line at 1440 px.

Next recommended phase: **Create in the luxury language** (presentation only). Its composition, voice selection, blueprint, rendering and project behaviour stay as they are. Checkpoint with the owner before My Music / Projects. ACE-Step, lyric phonemes and V5 stay parked until the owner decides on them.


## Session 024 — lyric intelligibility diagnosis

**Date:** 2026-10-13
**Trigger:** the first full song generated in Auralis (3:11 master) sounds like the owner's trained voice and is in key and in tune, but the vocals are wordless, like ad-libs rather than the entered lyrics. Task: diagnose before adding features. No retraining, no new models, no expensive GPU work.

### Verdict

**The current guide singer cannot produce intelligible lyric-conditioned singing.** This is the main cause, and it is by design. `VocaliseSinger` (`auralis/voice/singing_provider.py`, `sings_words = False`) renders every note as one of six static vowel formant sets (a e i o u uh), plus three kinds of noise burst standing in for consonants. There are no real consonants, diphthongs, nasals, liquids or word endings. Seed-VC copies the *content* of its source, so it cannot add words the guide never contained. The pipeline already records `guide_sings_words: false` in each song's `song.json`; the UI does not surface it.

A second, independent defect corrupts the words even before audio: **lyric lines are not mapped one-to-one onto melody phrases.**

### Path traced (lyrics → master)

1. **Create → `composer.brief.parse_lyrics`:** the lyrics are split into sections, then `blueprint.sections[].lyrics` holds the lines. Nothing is lost here.
2. **`composer.arrange._melody`:** one phrase per bar (verse) or per two bars (chorus/bridge), so the number of phrases comes from the section length, not the line count.
   - A phrase with a line gets about one note per estimated syllable, capped at 14.
   - Phrases beyond the last line get a *random* 5–8 notes.
   - Odd chorus phrases repeat the first phrase's hook notes, whatever their line's length.
3. **`voice.guide.build_score`:** it re-splits the melody into phrases at rests and gives phrase *n* the line `lines[n % len(lines)]`, so lines **loop** when phrases outnumber lines. Syllables beyond the phrase's notes are dropped; notes beyond the syllables get no syllable.
4. **`VocaliseSinger.sing`:** vowel formants plus noise onsets. No words.
5. **Seed-VC conversion → Pitch Polish (key) → Vocal Finish → mix/master.**

### Evidence

All local and repeatable; scripts and audio are in the session scratch folder, not the repo. Words were scored by the cached faster-whisper `base` model (CPU), counting phrase words recognised in order. Pitch is per-note median error in cents.

Test phrase: "take my hand and hold me close", 7 notes in D major (D4–G4), 90 BPM. It was converted with the existing Prinze Paired Studio voice, read-only: no retraining, nothing written to the voice or its history.

| Stage | Words in order | Notes |
|---|---|---|
| Vocalise guide (what the song used) | **0/7** ("ah, oh, oh…") | every note within 2 cents |
| … after Seed-VC | 0/7 | within 12 cents |
| … after Pitch Polish / Vocal Finish | 0/7 | |
| Windows TTS speaking the phrase (control) | 7/7 | not sung |
| Prototype speech-to-singing guide (TTS words, formant-preserving shift onto each note, only the vowel stretched; Zira, target octave) | **7/7** | within about 120 cents (speech intonation) |
| … after Seed-VC into the owner's voice | **6/7** ("take my *end* and hold me close": the soft /h/ was lost) | within about 110 cents |
| … after Pitch Polish and Vocal Finish | 6/7 | no further loss |
| Same prototype, male voice an octave down, Seed-VC +12 semitones | 7/7 guide → **3–4/7** | the large conversion shift damages words |
| First naive prototype (plain phase-vocoder shift of about +20 semitones) | 1/7 | formants pulled up ("chipmunk") |
| The produced song (`song.wav`, master) | Whisper judges 70% of it non-speech and loops a hallucinated phrase | consistent with wordless vocals |

**Lyric plumbing** (generic invented lyric through the real composer, seeds 0–2; verses of 16 bars, choruses of 8 bars):
- Verse lines were sung 1.5–4× over, out of order.
- One chorus line per chorus was cut short by the hook repeat.
- Only 15–16 of 20 lines were sung intact, and the guide sang about 285 syllables for a 176-syllable lyric.
- The regression test shows a 4-line verse singing 112 syllables for 41 written, with its first word dropped.

**Which stage degrades intelligibility:**
- The guide singer: entirely.
- Seed-VC: slightly (one weak consonant, /h/), and heavily when it has to shift pitch an octave.
- Pitch Polish and Vocal Finish: no measurable loss.
- Pitch Polish (key mode) did **not** pull speech-intonation errors of about 1 semitone onto the score's notes, so a word-capable guide must hit the notes itself, or correction must follow the score rather than the key.

### Regression tests added

`tests/test_lyric_intelligibility.py`: 3 pass and 2 are strict expected failures. Strict means pytest flags them once the fix lands, so the markers can come off.
- `test_guide_singer_sings_the_words` **(xfail, strict):** the registry's guide singer must sing the phrase with at least 6 of 7 words recognised. Currently 0/7.
- `test_each_lyric_line_is_sung_once_in_order` **(xfail, strict):** every entered line is sung once, complete, in order.
- `test_guide_keeps_the_target_melody`: every note within 25 cents. Passes.
- `test_the_word_meter_hears_real_words`: a Windows TTS control at 6/7 or better, so a failing gate means the singer, not the meter. Passes.
- `test_the_phrase_lands_one_syllable_per_note`: passes.

The recogniser and TTS tests skip cleanly where the local model or Windows speech is missing.

### Proposed fix: smallest viable local solution (not implemented; needs owner approval)

1. **A word-singing guide provider behind the existing seam** (`SingingProvider` / `REGISTRY.guide_singer()`, `sings_words = True`). No new architecture and no model download:
   - each syllable or word is spoken by a local TTS engine
   - a formant-preserving pitch change puts it on its note, flattened to the score's pitch (a per-frame method such as PSOLA in numpy, or the small MIT `pyworld` package)
   - only the vowel is stretched to the note length; consonants stay crisp
   - it sings in the target octave, so Seed-VC needs no large shift
   - The prototype already reaches 7/7 in the guide and 6/7 in the owner's voice.
   - Opt-in at first; vocalise stays the default until approved.
2. **Fix lyric → note mapping** (`arrange._melody` + `guide.build_score`): one phrase per line, no looping, hook repeats only for repeated lines, no silent truncation. **Version it** (an arranger version stored in the blueprint) so existing projects re-render with the same melody.
3. **Correct to the score, not just the key**, for word-sung guides, or guarantee the guide is already on the notes (item 1).
4. **Surface `guide_sings_words`** in Create and the Song studio, so a wordless guide is never a surprise.

**TTS engine choice:**
- Windows SAPI voices are built in and fine for the owner's local use, but their terms for commercially released output are unclear.
- espeak-ng is GPL-3, small, cross-platform, and robotic, but runs as a separate process like Seed-VC.
- Either can feed Seed-VC.
- Natural, expressive sung diction (Suno-like) needs a real singing model later, such as DiffSinger with a commercially licensed English voicebank (see `docs/MODEL_OPTIONS.md`). That is a larger step and stays parked.

**Available today without changes:** record or pick a sung guide (My Voice → Record or My Music lead stems); real words convert intelligibly.

### Gate

Owner decision on items 1–4 before implementation. Item 2 changes melodies of new renders, so it needs the versioning decision.


## Session 025 — lyric intelligibility fixes 1-4 (owner-approved)

**Date:** 2026-10-13/14
**Scope:** implement the four approved fixes from Session 024 in small, verified stages:
1. mapping
2. experimental word guide
3. melody-targeted pitch
4. notices

Constraints: Prinze Paired Studio data untouched (read-only conversion only), no model downloads, private lyrics outside Git, no commercial use of Windows-TTS vocals, nothing pushed without authorisation.

**Pushed first (authorised):** `e5dde00` and `456dfc3`. `origin/main` = `456dfc3` = local at that point.
- Privacy scan of both commits: no audio, lyrics, models or credentials. The voice profile's name was already public.
- Full suite: 253 passed, plus 1 order-dependent flake (`test_full_pipeline`, unseeded drum noise). It passed alone and was fixed separately in `1aabbe1`.

### Commits (local, not pushed)

- `1aabbe1` Tests: seed the full-pipeline drum stem. The loudness flake is fixed: identical stem and -14.0 LUFS under six global RNG states.
- `ae47103` **Fix 1: lyrics → melody, versioned.**
  - **New blueprints:** they carry `melody_version: 2`.
    - one phrase per lyric line, exactly one note per syllable
    - the bars are shared between lines, with a 2-beat rest after roomy lines
    - repeated lines reuse their melody within the same section type
    - an explicit note → (line, syllable) map: `arrangement["melody_lyrics"]`, consumed by `build_score`
  - **Saved blueprints** (no `melody_version`) run the untouched v1 code: melody, score and other tracks are byte-identical (fixture fingerprint).
- `ea8d555` **Fixes 2 + 3: experimental word guide and melody-targeted pitch.** Opt-in; vocalise stays the default. Details in `docs/AURALIS_CURRENT_ARCHITECTURE.md`, "Lyric intelligibility (Sessions 024-025)".
- `181262c` **Fix 4: guide choice and honest notices** in Create (Make the whole song and the blueprint Sing panel) and in Song Studio. Songs made before this phase show the wordless notice.

### Results

**Fix 1, mapping** (generic lyric through the real composer, seeds 0-2):
- 20/20 lines intact and 176/176 syllables. Before: 15-16/20, with 285 syllables sung for 176 written.
- An ad-lib regression was found and fixed during the stage: v2 first left only a 1-beat rest, and ad-libs disappeared in 14/40 random songs. With the 2-beat rest: 40/40, same as v1.

**Fix 2, word guide** (dry guide, Whisper `base` word recall in order, pyin against the *written* notes):

| Material | Guide | Words in order | Notes within 25 cents |
|---|---|---|---|
| Phrase (7 words) | vocalise | 0/7 | 100% |
| Phrase | **word guide** | **7/7** | **100%** |
| Verse + chorus (56 words, 71 notes, melody v2) | vocalise | 0/56 | 100% |
| Verse + chorus | **word guide** | **53/56 (94.6%)** | **100%** (median 2.5 cents) |

- Two fixes along the way:
  - pyin marked the start of short words unvoiced, so "take" and "my" kept the speech pitch, about 10 semitones low. A periodicity measure was added.
  - "the" spoken alone was heard as "they". Weak forms are now respelled for the speech voice.
- Remaining misses: "the" sometimes heard as "through", and the end of "river bends" is soft.
- Speed: 11 s to sing the 45 s verse + chorus.

**Fix 3, score pitch** (`pitch_to_score`):
- notes detuned 60-140 cents (some towards a neighbouring scale tone) return to the written notes: at least 85% within 25 cents, median 20 cents or less
- the vowel envelope is unchanged (MFCC correlation above 0.9 per note)
- words recognised after correction ≥ before (tests)

**Fix 4, notices:** checked in the real app with Playwright. Both guide options are listed with their notices, and the choice is remembered and sent. The owner's existing song opens in Song Studio with "Wordless guide: this song was sung before word guides existed…".

**Before/after voice conversion with the new guide (measured 2026-10-14, when 9-12 GB was free):** converted into Prinze Paired Studio, read-only. Words in order, and notes within 25 cents of the *written* melody:

| Stage | Phrase, word guide | Verse + chorus, word guide | Verse + chorus, vocalise | Notes within 25 c |
|---|---|---|---|---|
| Dry guide | 7/7 | 52/56 (92.9%) | 1/56 | 100% |
| After Seed-VC | **6/7** | **49/56 (87.5%)** | 0/56 | 100% (median 7.5 c) |
| After score pitch | 6/7 | 53/56 (94.6%) | 0/56 | 100% (median 2.5 c) |
| After Vocal Finish | | **52/56 (92.9%)** | 1/56 | |

- **Seed-VC:** it costs a few weak consonants: the /h/ of "hand" ("take my end"), and "the" heard as "through".
- **Score pitch and Vocal Finish:** they cost no words. Differences of a word or two are recogniser noise.
- **Pitch:** it stays on the written melody at every stage.
- **Evaluation flaw found and corrected:** the first overnight run measured the verse + chorus against a different melody. `arrange` seeds from the blueprint's random id, and the evaluation script rebuilt the blueprint per run. That run's pitch numbers (about a 197-cent median) were invalid and are discarded. The table comes from a rerun with the blueprint id pinned, so guide, conversion, pitch and measurement share one melody. Repo tests build and measure within one call, so they were not affected.

**Tests:**
- `tests/test_lyric_intelligibility.py`: 13 pass + 1 strict xfail. The xfail is the *default* guide still being vocalise, by owner decision.
- `tests/test_word_guide.py`: 10 pass, 1 opt-in live Seed-VC test (`AURALIS_LIVE_VOICE=<voice name>`).
- Full suite on the committed code: 273 passed (+ the fingerprint test fixed and re-run), 1 skipped, 1 xfail.
- vite build clean.

### Listening samples (local, git-excluded)

`samples/session-025/` (generic invented lyrics):
1. phrase, current vocalise guide
2. phrase, word guide
3. verse + chorus, vocalise
4. verse + chorus, word guide

In your voice (Prinze Paired Studio, read-only):
5. phrase, word guide, converted and score-pitched
6. verse + chorus, vocalise, converted and finished
7. verse + chorus, word guide, converted and finished
8. verse + chorus, word guide, raw conversion

### Outstanding limitations

- **Sound:** the word guide is plain and robotic. Each word is spoken alone (no linking between words, no expressive delivery). It makes the words understandable; it is not a performance.
- **Licence and platform:** Windows only (SAPI voices). Their licence for distributing generated audio is unreviewed, so songs sung with it are personal, local use only (`personal_use_only: true`). No commercial use until reviewed.
- **Backing parts:** doubles and harmonies are sung with words by the word guide, but only the lead gets score pitch correction.
- **Lyric text:** digits in lyrics ("24/7") are dropped by `syllabify`; this predates this session.
- **Demo sections:** a demo-to-song section keeps the demo's own melody and the old syllable assignment.
- **Song Studio:** it cannot reopen an older project (it opens only right after making a song). This predates this session.
- **Measurement:** words are judged by Whisper `base`, a proxy for a listener. The owner's ears decide.
- **Suite time:** the full suite now takes about 47 minutes, because the word-guide tests use speech recognition.

### Gate

Owner listening approval of the word guide (dry and converted samples ready) before it becomes the default. The `test_guide_singer_sings_the_words` xfail flips when it does.

### Next recommended

1. ~~Finish the conversion comparison~~: done 2026-10-14 (table above).
2. Owner listening review.
3. If approved: make the word guide the default for songs with lyrics, keeping vocalise selectable, and remove the xfail.
4. Then the licence review, or a licence-clean engine (espeak-ng, or a commercially licensed singing voicebank) for release.

## Session 026 — 2026-10-16 — Plugin Intelligence Phase 1

### Starting state and scope
- Existing F:/Auralis repository, branch main at `5a93b02`; clean working tree before changes. Read both continuity files before implementation. No user changes overwritten, no destructive Git commands, no push/merge.
- Graph indexed with the codebase-memory skill (fast, Tier 2), coverage checked, relevant source read directly because freshness metadata reported changed. Existing FastAPI/React architecture; Pedalboard built-in DSP, no third-party discovery/catalog code found in searched application/test source. No new app or host.
- Existing owner listening gate on the experimental word guide remains unchanged; personal voice training/cloning, song workflows and shell design preserved.

### Exact files changed
- `auralis/plugins.py`: bounded passive Windows scanner, PE architecture + allowlisted version resources, VST3 moduleinfo class metadata, unknown/candidate states, possible duplicates, classification/search and five inventory-only planning templates.
- `auralis/api/plugins.py`: session-only catalog, explicit scan, filter and chain endpoints.
- `auralis/api/main.py`: include the plugin router.
- `frontend/src/PluginLibrary.jsx`: explicit scan, session-only custom roots, search/category filter, entry details, compatibility and vocal-chain planning.
- `frontend/src/PluginLibrary.css`: responsive view using existing luxury tokens/surfaces.
- `frontend/src/App.jsx`: register Plugin Library in existing Tools navigation and render it.
- `tests/test_plugins.py`: synthetic scanner, privacy, safety, metadata, classification, duplicate, inventory-only recommendation and API coverage.
- `docs/PLUGIN_INTELLIGENCE.md`: usage, trust boundaries, integration research with official links, limitations, aggregate discovered inventory; detailed product snapshot retained locally, next gate.
- `AURALIS_SESSION.md`, `auralissession.md`: continuity update.

### Implementation and actual discovery
- Read-only standard VST folders plus explicit additional dedicated roots; no whole-drive scan, registry reads/writes, arbitrary plugin code loading, activation, installations or DAW automation. Reparse/network/broad/private roots rejected; bounded enumeration/metadata. Only plugin-related metadata is inspected; no license/personal document contents.
- 49 entries: 32 VST3 and 17 unverified DLL/VST2 candidates; 40 x64, 8 x86, 1 architecture Unknown. Sixteen entries in possible duplicate groups (not byte-identity claims).
- Examples confirmed as file candidates: Auto-Tune Access 9.0.2, Artist 9.0.2, Pro 10.3.1, EFX 9.0.1, SoundSoap 6.0.0, Vocal Compressor 1.0.1; FabFilter Pro-Q 2 2.0.1.24; Softube Tube-Tech CL 1B 2.5.9. Versions are self-reported Windows resources, not loaded plugin verification.
- VocALignPro and VocALignProP candidates are x86, version Unknown. No proof of exact edition, licensing, ARA or Mixcraft compatibility. Waves/Soundtoys not verified in scanned standard roots; no claim they are absent from this machine. Detailed candidate snapshot retained locally; aggregates in the phase document.
- Classification recognizes pitch correction, alignment, EQ, compression, noise reduction, reverb and effects in this snapshot; many entries remain Unknown. Vendor branding alone never implies pitch correction (Auto-Tune-branded EQ/compressor/SoundSoap correctly separated).
- Planner chooses deterministic classified x64 VST3 candidates, flags missing/unverified steps, and explains purpose. DLLs and x86 candidates are excluded. No audio has been processed by these recommendations.

### Verification
- `python -m pytest tests/test_plugins.py -q`: **27 passed**.
- `npm run build`: **passed**, 49 modules.
- `git diff --check`: passed (line-ending notices only).
- Wider existing regressions: result appended below when complete. An initial command named nonexistent `tests/test_pipeline.py` and collected no tests; corrected to `tests/test_engine.py`.
- No real Mixcraft hosting/routing/ARA/activation/listening trial performed. Plugin Library runtime/visual review not performed; build/API checks only. Full expensive speech-recognition suite not rerun for this isolated feature.

### Mixcraft / REA research
- Acoustica documents VST/VST3 loading, editable folders, rescanning and Plugin Manager. None of those settings changed.
- Mixcraft 10 has a supported JavaScript MIDI/SysEx controller-script API. A general external RPC or arbitrary chain insertion/preset/audio-host API was not established. Prefer supported controls before investigating internals.
- Synchro Arts Project 5 docs distinguish ARA from realtime sidechain capture; they cannot establish the locally discovered older x86 Pro edition's support.
- Antares x64 VST3 files are plausible host candidates only; licensing and installed edition compatibility unverified.
- Read the reverse-engineer-anything skill and reviewed exposed REA capabilities. No Mixcraft desktop automation adapter or audio engine verified; no targets opened/debugged/instrumented. REA remains a future investigative candidate, not a DAW/audio engine.
- Primary source links and detailed findings in `docs/PLUGIN_INTELLIGENCE.md`.

### Limitations and next gate
- Inventory and custom roots are backend-session-only; no persistence. VST2 exports are not checked. Shell subplugins may be unresolved. Strict JSON subset of optional JSON5 moduleinfo only; unsupported/invalid data stays explicit. No compatibility claims from file presence or filenames.
- Selection is alphabetical among eligible candidates, not an audio-quality ranking. Unknown/unidentified functions remain gaps even if a plugin may actually implement them.
- Phase 1 stops here. Owner review of inventory/extra dedicated roots and a separately approved manual compatibility/listening test on copied stems is the safest next step. Determine VocAlign edition/architecture and supported routing/bridge first. Plugin execution, configuration or automation is outside this phase.
- Changes left local and uncommitted for owner review; no push or merge.

### Session 026 final verification result
- Existing regressions: `python -m pytest tests/test_voice_library.py tests/test_models.py tests/test_harmony.py tests/test_engine.py -q` — **66 passed**, 11 dependency/synthetic-short-audio warnings, 214.82 s.
- Plugin suite on final code: **27 passed**. Final passive scan still 49 entries, 32 with known resource/declared manufacturers. Frontend final build passed.
- Phase 1 complete; no real Mixcraft or UI visual check claimed. Local changes remain uncommitted for owner review.

## Session 027 — 2026-10-16 — Match the demo: timing + melody

### Owner request and starting state
- Owner narrowed new work to one feature: demo/AI vocal + their sung WAV -> their vocal following the demo. Clarified **timing and melody**, preserving their own voice. No broader plugin expansion requested.
- Main at `5a93b02`; prior Session 026 inventory work remained uncommitted. Preserved it in place. No other features or word-guide/training defaults changed; no push/merge/commit.
- Used codebase-memory graph/coverage + direct source reads to inspect existing pitch tracking, formant preservation, FastAPI jobs and React tool navigation. Source fallback used for changed freshness metadata. Existing pitch code itself remains unchanged.

### Exact changes for this request
- NEW `auralis/voice/reference_match.py`: bounded WAV validation/decoding; acoustic-feature DTW; monotonic speed-bounded mapping; existing `_track_pitch`; guide melody targeting; formant-preserving offline rendering via already-installed Pedalboard, new output/report only.
- NEW `auralis/api/reference_match.py`: staged two-WAV upload, validation before job creation, single active matching job, existing JOBS lifecycle, guide/take/result previews/download and report.
- NEW `frontend/src/ReferenceMatch.jsx`, `frontend/src/ReferenceMatch.css`: existing luxury design and WavePlayer; two uploads -> one button -> progress -> previews and downloadable WAV; remembered session job when navigating away/back.
- NEW `tests/test_reference_match.py`: real rendered-audio and API checks, source protection, stereo/rates, invalid input, monotonic limits and worker-failure recovery.
- NEW `docs/REFERENCE_VOCAL_MATCH.md`: usage, implementation, REA findings, verification/limitations.
- MODIFIED `auralis/api/main.py`: register new router, preserving Session 026 router changes.
- MODIFIED `frontend/src/App.jsx`: add Match the demo tool/view, preserving all earlier navigation.
- MODIFIED both session files: this entry/summary and final results.
- Synthetic samples/reports in git-excluded `samples/session-027/`; no owner audio, model or lyric files processed/modified.

### REA and actual VocAlign status
- Used reverse-engineer-anything skill. REA opened installed VocALignPro.vst3 read-only: PE/x86, SHA-256 `4fb638950cda9acd9beb4c9d2518a4b76f147f09d1ddc317fd72042e5097f6be`.
- Focused REA string analysis returned `provider_unavailable`: Ghidra not configured, Hopper unsupported on Windows, IDA not configured. Read the skill recovery guidance; no installation/configuration performed.
- No proprietary algorithm was recovered or copied. No plugin instantiated, license/activation inspected, or Mixcraft workflow automated. Public Synchro Arts guide/dub documentation informed the interaction, not an assertion of installed-plugin compatibility.
- Explained the limitation to the owner while working. Implemented an independent Auralis processor using existing local libraries; the result/report explicitly marks `plugin_used: false`. Actual VocAlign hosting/bridge remains unverified, separate work.

### Behavior and limits
- Tools -> Match the demo: isolated demo WAV + isolated take WAV, same words/order/section, up to 180 seconds each. 100 MiB upload cap; mono/stereo, 8–96 kHz, bounded decoded sample budget.
- Takes only timing and melody targets from guide analysis; audio in output comes only from the owner's take. Output matches demo duration/timeline while retaining take rate/channel count. Does not train or clone voices.
- Speed limited to 0.5–2x, pitch shift to one octave either way, no silent octave folding. Uncertain pitch left unchanged; reduced timing moves/limited pitch and weak acoustic match are surfaced. Acoustic matching cannot verify identical words.
- An early rendered-audio test detected a phase-cancellation dropout in overlapping stretched regions. Added phase alignment (up to 4 ms) before crossfading; the strict onset-count test now passes.
- Synthetic three-note take: before onsets `[0.40, 1.45, 2.21]`, demo `[0.21, 0.95, 1.85]`, output `[0.20, 1.01, 1.82]` seconds. Mean onset error **350 -> 33 ms**. Target MIDI `[60,64,62]`, output measured `[60.02,64.01,62.02]`. Distinct source harmonic colour retained, source bytes unchanged. These are synthetic metrics, not a real-singer listening guarantee.

### Verification and handoff
- Initial reference suite after phase fix: 11 passed. Added a separate passing worker-error/busy-gate regression (12 total tests).
- Frontend build: passed, 51 modules. Existing/new combined regression outcome appended below when complete.
- Real Chrome rendering/navigation/initial disabled action checked against isolated local Auralis servers. Browser upload automation blocked by extension file-URL access permission; did not change that setting. Real FastAPI upload -> processing -> result/report/preview download verified by tests. No full browser-upload or owner-vocal listening claim.
- Existing voice, conversion, training and word-guide code remains intact. No new dependencies, paid calls, original audio writes, DAW automation or plugin changes.
- Experimental region-based acoustic matcher: consonants, breaths, runs, differing lyrics, large register changes and backing music need owner listening review. No claim of VocAlign-equivalent sound. Next: owner supplies a short isolated demo and matching take for listening/real-vocal validation. Do not expand beyond this requested feature.

### Session 027 final results
- Combined targeted regressions: **69 passed**, one existing Matchering/SciPy deprecation warning, 161.90 seconds (`test_plugins`, `test_reference_match`, `test_pitch_polish`, `test_voice_library`, `test_models`). The subsequently added worker-error recovery regression also passed separately: **70 passing targeted checks total**.
- Frontend build passed, 51 modules. `git diff --check` passed. Test Chrome tab and isolated test servers closed/stopped after inspection. No production Auralis server or DAW was restarted.
- Changes remain local/uncommitted. Feature implementation complete as experimental Auralis reference matching; real-vocal listening and actual VocAlign hosting are unverified.

## Session 028 — 2026-10-16 — Owner vocal pair tested

- Owner supplied `demo vocal.wav` (AI, 248.999955 s) and `my dry vocal1.wav` (live, 499.251859 s), then requested comparison of both apparent portions of the live file. Tested locally, without plugin execution, DAW edits, model downloads or network transcription. Originals remain byte-identical (SHA-256 before/after verified).
- Initial length/energy inspection suggested two apparent performances. Owner then supplied the open BandLab Studio project. Read-only browser DOM inspection clarified the arrangement: the AI guide region ends at 248.999977 s; Lead Dry has seven regions ending at 239.694657 s and extra regions from 250.344828 to 499.251877 s. All inspected clip playback rates are 1; tempo 58 BPM. Thus the long WAV contains extra timeline clips after the guide ends, not established to be two corresponding takes or a half-speed export. No BandLab selection, mute/solo, effects, clip position, tempo, save or publish state changed.
- Relevant overlap is 0–249 s. Produced full-length stereo 44.1 kHz/24-bit output, using derived 0–150 and 150–249 s sections split at the shared silent pause to respect the current app's 180 s job limit. Exact guide frame count 10,980,898, finite samples, peak -12.99 dBFS, assembly boundary silent. This batch test does NOT add long-file upload support or automatic take selection to the app.
- Opening 35 s test: median guide-relative pitch error 40 -> 10 cents; within 50 cents 55.7% -> 92.6%; local ASR guide-word overlap 10/32 -> 24/32; mean word-centre error 186 -> 67 ms across only eight shared recognized words. Those are automated proxies, not manual lyrics or listening. Rechecked the full render's first 35 s: 40 -> 10 cents, 56.3% -> 93.4% within 50 cents on 542 common confident frames.
- Later passage 248–283 s compared separately: 3/32 guide-recognized-word overlap both before/after, different recognized lyrics, at best 15.4% correspondence against any similarly sized window of the full demo transcript. Diagnostic only; no corresponding guide exists at this part of the project timeline, so not a recommended matched take.
- Full render adjusted pitch in 338 regions, left 568 uncertain-pitch regions untuned and capped three corrections. No full-song intelligibility or subjective listening validation claimed. Owner should audition consonants, runs, breaths and later sections; processing success is not an assurance of professional quality.
- Private outputs/reports/transcripts/hashes in git-ignored `jobs/real-vocal-check-gavyzq3v/`; final `your_vocal_matched_to_demo.wav`, test report `REAL_VOCAL_TEST.md`, machine details `manifest.json`, separate short A/B excerpts and diagnostic later-passage render. No owner audio or lyric transcripts added to Git. Both session files updated; feature source unchanged in this testing turn. No commit/push/merge.

## Session 029 — 2026-10-16 — Prinze dataset import and GitHub publication

### Dataset import (local data only)
- Owner authorized adding the two supplied live-vocal takes to the existing Prinze profile. Verified the shorter recording is an exact PCM prefix of the longer one, so imported one unique raw recording covering both instead of duplicating the opening.
- Existing profile: Prinze Paired Studio, 137 clips / 965.38 prepared seconds. Used the existing `VoiceProfileStore.add_take -> add_recordings -> refresh_analysis` workflow. Basic capture checks passed; no clipping. Compared candidate clips to existing clips of equal length using waveform correlation; no duplicate matches found within that bounded check.
- Added 64 mono 44.1 kHz training clips, 427.94 seconds (1.3–20 s each), finite/peak-safe. After: **201 clips / 1393.32 seconds (23:13)**, readiness **84**. Raw unique take archived within the local profile; originals unchanged by SHA-256. Detailed validation/metadata backup/provenance are local, outside the published source.
- Existing reference, checkpoint and model configuration hashes unchanged; model remains the prior 1,000-step checkpoint. **No retraining was started**, and newly added data is not claimed to have changed the trained voice yet.
- No feature code changes were needed for importing. No recordings, prepared clips, model weights or transcripts enter Git.

### Publication requested by owner
- Owner explicitly asked to update GitHub once complete and then to continue. `origin/main` was six commits behind local main; inspected their scope: previously documented Session 025 drum-test fix, versioned lyric mapping, opt-in word guide, guide-choice notices and evaluation notes. These previously verified commits are included in the normal fast-forward publication together with the new work. No force push or merge requested/performed.
- New publication includes Plugin Library/catalog/classification, experimental Match the demo engine/API/UI, tests, README usage links, research/limits and Sessions 026–029 continuity. Existing personal voice/cloning and word-guide default/listening gate preserved.
- Detailed installed-plugin inventory moved to an ignored local review snapshot; public docs retain aggregate discovery results and integration research. Audio, datasets, checkpoints, local recognition transcripts, source hashes and detailed private test reports remain local/ignored.
- Final targeted regression/build results and GitHub outcome appended below.

### Session 029 final verification
- Final combined targeted run: **107 passed**, 11 existing dependency/short-synthetic-audio warnings, 283.09 s (`test_plugins`, `test_reference_match`, `test_pitch_polish`, `test_voice_library`, `test_models`, `test_harmony`, `test_engine`). Full expensive speech-recognition suite not repeated; earlier Session 025 evidence remains documented for its unchanged commits.
- Frontend production build passed (51 modules); staged whitespace check passed. Entire publication range against origin/main audited: 38 source/text paths, no personal audio/model/private-job files and no recognizable credential patterns. Current implementation commit contains 17 intended source/test/doc paths.
- Dataset import verified complete: 201 clips, 1393.32 prepared seconds, readiness 84; protected model/reference/config and supplied-source hashes unchanged. No retraining.

### Session 029 GitHub outcome
- Implementation commit `78694c0` (`Add local plugin discovery and demo vocal matching`) successfully pushed to `origin/main`, advancing GitHub from `456dfc3` through the six pending Session 025 commits and the verified new work. Normal fast-forward push, no force and no PR merge.
- This follow-up continuity entry records the successful publication. Local training recordings, dataset/model assets, transcripts and detailed private reports were excluded; the Prinze import remains local. Current trained model is still the existing 1,000-step checkpoint; new data awaits a future explicitly requested retraining run.


## Session 030 — 2026-10-17 — Verification of main, numbers in lyrics, small fixes

**Owner instruction:** "continue". No new decision was given on the open gates (word guide as default, retraining the imported Prinze data, plugin trials), so they stay open. This session did only decision-free work.

**Starting state:**
- `main` = `origin/main` = `13f9fed`, clean.
- Sessions 026-029 (plugin discovery, Match the demo, the Prinze dataset import, publication) were read first. They had run targeted test subsets only.

### Verification of the published main

- Full suite on `13f9fed`, frozen snapshot: **313 passed**, 1 skipped (the opt-in live-voice test), 1 xfail (the default guide is still vocalise). 19 min 54 s.
- Sessions 026-029 introduced no regressions.

### Changed

1. **Melody v3: numbers in lyrics are sung as words.**
   - v2 counted syllables from letters only, so "I was 19 in 1999" was sung "i was in", "my 2nd chance" as "my nd chance", and "24/7" lost both numbers.
   - `voice.guide.spell_numbers` reads them as a singer would: "twenty four seven", "nineteen ninety nine", "second", "ninety nine", "twenty first", "one hundred". It covers up to 9999; longer digit runs are read digit by digit.
   - It applies only from `melody_version` 3, now stamped on new blueprints. v1 and v2 songs keep their saved behaviour. This is proven by a v2 fixture with digit lyrics, fingerprinted with the published v2 code (13f9fed) and identical under the new code.
   - Known reading: "911" becomes "nine hundred eleven", and "2010" becomes "two thousand ten".
2. **The sidebar voice card follows the shared voice selection**: your remembered choice > trained > studio dataset > first, the same as My Voice and Create. It updates live when the voice changes in My Voice. Before, it always showed "trained or first".
3. **Favicon** (`frontend/public/favicon.png`, 64 px from `docs/icon.png`). The only console error the app had is gone.

### Verification of the changes

- `test_lyric_intelligibility` + `test_word_guide`: **32 passed**, 1 xfail.
- The new tests are number spelling (7 cases), v3 sings every number as words, and saved v2 songs with numbers are byte-identical.
- Full suite on the changed code (frozen snapshot): **322 passed**, 1 skipped, 1 xfail, 19 min 35 s.
- Real app (Playwright, 1440 px): favicon 200; **no console errors or failed requests** across Create, My Music, Artist DNA, Studio, My Voice and Projects; the sidebar card shows the remembered voice.
- vite build clean.

### Still waiting for the owner (unchanged)

- **Word guide as the default for songs with lyrics:** the listening gate. Dry and converted samples are in `samples/session-025/`; measured 92.9% of words after Seed-VC and Vocal Finish.
- **Retraining Prinze Paired Studio** with the 64 clips imported in Session 029 (now 23:13 of singing). This is GPU-heavy and needs an explicit request.
- **Plugin compatibility and listening trials** (Session 026), and Match the demo listening (Sessions 027-028).


## Session 031 — 2026-10-17 — Backing-part tuning, reopen saved songs

**Owner instruction:** "continue". This session did decision-free items from the Session 025 limitations. The owner gates are unchanged.

### Changed
- **Word-sung backing parts are tuned to their own written notes** (`full_song`, word guide only):
  - The lead already was. Doubles and harmonies come from speech too and could drift.
  - `backing_pitch_accuracy` is recorded per part. Vocalise songs keep the old path.
- **Projects → Open in Song studio** for any project holding a finished song. This closes the Session 025 limitation that Song Studio opened only right after making a song.

### Verification
- **Backing accuracy across four blueprints:** the lead and every word-sung part reached 100% of notes within 25 cents of their written notes. Ad-libs reached 80-100%: they are fast wordless runs of about 0.15 s, where pitch tracking itself is noisy.
- **The first test run failed** on one ad-lib case (80% against an 85% bar). The test now asks for at least 85% on word-sung parts and at least 70% on ad-libs; it passed twice after that.
- **Affected test files** (full song, vocal production, song assembly, projects, lyrics, word guide): 67 passed, 1 skipped (opt-in live voice), 1 xfail (default guide).
- **Real app (Playwright):** Projects → the owner's existing song → Open in Song studio opens the right project with its wordless-guide notice; no console errors.
- vite build clean.

### Still waiting for the owner
- Word guide as default.
- Retraining Prinze Paired Studio with the Session 029 data.
- Plugin and Match-the-demo listening trials.
- Pushing the local commits (4 after `13f9fed`).
