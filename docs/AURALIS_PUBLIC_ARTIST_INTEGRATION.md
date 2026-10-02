# Auralis Public Artist Integration & Sustainable Hosting Plan

**Status:** Approved product direction — planning only  
**Date:** 2026-10-02  
**Canonical repository:** `ingenuousmorpheus/Auralis`  
**Related artist site:** `ingenuousmorpheus/ingenuousprinze`

## 1. Goal

Connect the Ingenuous Prinze artist website to Auralis so visitors can discover the music and enter an Auralis experience associated with the artist.

Target flow:

```
INGENUOUS PRINZE
Music / Releases / Photos / About / Auralis
                         ↓
                     AURALIS
                         ↓
        Hear the music / experience the voice
                         ↓
          Optional public interactive demo
```

The artist site should become an early public showcase for Auralis rather than a separate product fork.

## 2. Critical architecture rule

Auralis is currently local-first. The README describes the FastAPI API as serving on `127.0.0.1`, and the existing launcher starts local backend/frontend processes.

Do **not** expose the user's home Auralis machine directly to arbitrary website visitors.

The public website and public Auralis experience must use a controlled public service boundary. The user's private/local installation remains private.

There are therefore two distinct modes:

### Local Auralis

- Full local installation
- Private voice and audio data
- Local GPU/CPU processing
- No public hosting cost beyond the user's own hardware/electricity
- Existing architecture remains authoritative

### Public Auralis

- Public web UI
- Controlled API/service boundary
- Explicit resource limits
- Separate public processing environment when actual AI/audio processing is offered
- No access to the user's private local voice files, catalog, filesystem, or LAN
- Usage controls before expensive GPU processing is enabled

## 3. Do not make $10/month the initial assumption

The previous idea of a roughly $10/month public subscription is **not** a requirement.

Suno's current consumer pricing is a moving market reference, not a target price for Auralis.

Auralis should first establish the experience and actual operating cost.

Initial public strategy:

1. Keep the full product local-first.
2. Build a lightweight public artist/demo experience.
3. Measure real visitor usage.
4. Add cloud GPU processing only when needed.
5. Prefer usage-based/on-demand GPU capacity over an always-on expensive GPU.
6. Introduce paid public plans only after actual cost and demand are known.

The product differentiator is not simply "another $10 music generator."

The positioning is:

**LOCAL-FIRST / PRIVATE / YOUR VOICE / YOUR MUSIC / YOUR STUDIO**

The artist-facing message can emphasize:

**Hear my music. Experience my voice. Try Auralis.**

## 4. Cost model

The public website itself should be inexpensive.

The expensive component is audio/AI inference.

### Tier A — Artist showcase

Public site + Auralis information/demo pages.

Approximate incremental compute cost: near zero if static content is used.

Purpose:

- explain Auralis
- showcase Ingenuous Prinze music
- play approved demos
- demonstrate the trained voice
- collect interest without exposing processing infrastructure

### Tier B — Limited interactive demo

Visitors can submit a short, tightly limited audio request.

Use:

- short maximum input duration
- queueing
- rate limits
- per-IP/session abuse controls
- output duration limits
- optional daily/monthly quotas
- on-demand GPU workers

The goal is to prove demand before committing to permanent GPU capacity.

### Tier C — Full public Auralis service

Only after usage justifies it.

Possible architecture:

```
Artist website
     ↓
Public Auralis frontend
     ↓
Public API / job gateway
     ↓
Queue + resource limits
     ↓
On-demand GPU worker
     ↓
Auralis processing pipeline
     ↓
Temporary output
     ↓
Browser download/playback
```

The worker should process only the authorized job and should not have access to the user's private local environment.

## 5. Public vs local code

Do not create a second Auralis engine.

The existing architecture should remain the core.

Reuse:

- FastAPI APIs
- React/Vite frontend
- voice store
- Seed-VC provider
- model lifecycle/registry
- conversion queue/history
- My Music
- My Voice
- full-song pipeline
- vocal production
- mastering
- Studio → Advanced controls

The deployment layer should adapt the existing application to a controlled public environment rather than duplicating audio logic.

## 6. Artist-site integration

The eventual artist navigation can include:

- Music
- Auralis
- Photos
- Releases
- About
- Connect

The Auralis entry should lead to a real Auralis experience, not a dead/localhost link.

The artist site may pass non-sensitive context such as:

- artist identifier
- selected public song identifier
- referral/source
- optional campaign/demo identifier

Never pass private voice files, local filesystem paths, API keys, or private catalog data through URL parameters.

## 7. Artist identity and Auralis

Auralis can eventually support an artist showcase configuration such as:

```
artist_id = ingenuous-prinze
display_name = Ingenuous Prinze
public_catalog = approved releases only
public_voice_demo = approved voice demonstration
public_features = explicitly enabled demo features
```

This should be configuration, not a hard-coded fork of Auralis.

That leaves the same Auralis product capable of hosting other artists later.

## 8. Privacy and safety boundary

Public visitors must never gain access to:

- the user's local Auralis filesystem
- private voice datasets
- private trained checkpoints
- local music library
- LAN services
- local API endpoints
- model-management controls
- arbitrary shell/process execution
- private project files

Public uploads should be treated as untrusted input.

Temporary public jobs should have lifecycle cleanup.

## 9. Product rollout

### Phase P1 — Public artist showcase

- Add Auralis navigation to the artist site.
- Create public Auralis landing/showcase route.
- Feature approved Ingenuous Prinze music and voice material.
- No public GPU processing yet.

### Phase P2 — Interactive demo

- Public API boundary.
- Short demo jobs.
- Queue and limits.
- On-demand processing.
- Usage measurement.
- Abuse protection.
- Explicit consent for uploaded audio.

### Phase P3 — Public creation

Potential capabilities:

- short voice conversion
- demo-to-song experiments
- limited Auralis creation
- controlled song generation
- account/usage limits

Only enable expensive capabilities after cost measurements.

### Phase P4 — Commercial service

Evaluate:

- actual GPU cost per job
- average visitor usage
- storage/bandwidth cost
- abuse rate
- conversion success rate
- retention
- willingness to pay

Only then decide public pricing.

## 10. Relationship to current Luxury UI work

This plan does **not** replace Session 018's Luxury My Voice redesign.

The current priority remains:

1. My Voice luxury redesign
2. reusable design primitives
3. shell/navigation polish
4. Create
5. My Music/Projects
6. Studio/advanced
7. Release/Export
8. README/demo

Public artist integration is a deployment/product layer that can be implemented after the current UI foundation is stable.

## 11. Immediate next technical investigation

Before changing deployment architecture:

1. Determine how the production Vite build is currently served.
2. Determine how FastAPI serves/locates frontend assets, if at all.
3. Inventory existing CORS/authentication and API boundaries.
4. Identify voice-conversion endpoints that would be candidates for controlled public jobs.
5. Identify model lifecycle operations that must remain private.
6. Determine the smallest public demo that can run without exposing the local installation.
7. Evaluate on-demand GPU hosting only after the public demo boundary is defined.
8. Then add the Auralis tab to `ingenuousmorpheus/ingenuousprinze`.

## 12. Non-goals

Do not:

- turn the user's local PC into a public server
- rewrite Auralis around a cloud-only architecture
- add heavy model downloads without explicit approval
- purchase hosting/GPU capacity without explicit approval
- create a second voice state store
- duplicate the existing audio engine
- promise unlimited public processing
- set a final subscription price before cost data exists

## Decision

**Auralis remains local-first.**

The Ingenuous Prinze site will eventually become a public doorway into a controlled Auralis showcase/demo.

Public compute is optional, isolated, usage-controlled, and added only when real demand justifies its cost.

The first public version should prove the experience before it attempts to compete with centralized music-generation services on infrastructure scale.
