# Auralis Session

> Canonical lightweight continuity checkpoint for ChatGPT, Claude, Codex, and
> future Auralis work.
>
> Last reconciled from GitHub: 2026-10-06.
> Repository: ingeniousmorpheus/Auralis
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
