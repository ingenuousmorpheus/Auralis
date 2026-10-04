# Auralis Luxury UI Design — My Voice + Studio Visual Direction

Status: OWNER-APPROVED DESIGN DIRECTION · My Voice first pass BUILT (Session 020), awaiting owner visual validation
Date: 2026-09-30

## 1. Purpose

Auralis already has substantial music, voice, project, mastering, and model-lifecycle capability. The next product problem is presentation: it should feel like a premium local music studio rather than a developer-facing audio utility.

The first implementation target is My Voice. This screen becomes the reference implementation for a reusable Auralis visual language that can later spread to Create, My Music, Studio, Mastering, Projects, and Release.

The approved visual direction is the 2026-09-30 Auralis luxury mockup discussed with the owner.

Product aspiration: professional vocal studio + creative instrument + private/local AI music workstation + approachable first-run experience + advanced depth.

Long-term aspiration is to build an open-source product people want to star, share, extend, and contribute to. This is an aspiration, not a guaranteed outcome.

## 2. Competitive design references — learn, do not copy

Kits AI is a reference for strong voice identity, obvious input/output relationship, large drop zones, voice switching, training/improvement, conversion history, simple language, and a dark premium studio atmosphere.

Suno is a reference for creative-workspace composition, immediate creation, living audio assets, waveform interaction, and advanced controls without overwhelming the primary workflow.

Do not copy their branding, exact layouts, icons, wording, assets, or distinctive visual expression.

Auralis must own its identity: LOCAL-FIRST / PRIVATE / YOUR VOICE / YOUR MUSIC / YOUR STUDIO.

## 3. Approved visual language

Overall mood: luxury recording studio at midnight.

Not gaming RGB. Not generic SaaS. Not a flat developer dashboard.

Use near-black/obsidian surfaces, deep plum and violet atmosphere, restrained cyan/blue waveform accents, soft magenta highlights, glass-like dark surfaces, subtle gradients, thin luminous borders, generous spacing, large typography, restrained glow, and waveform motion where useful.

The interface should look expensive because of hierarchy, spacing, typography, lighting, and restraint — not because every element glows.

Define reusable theme variables for background, surfaces, borders, text, muted text, purple, violet, magenta, cyan, success, and danger. Do not scatter one-off colors through components.

## 4. My Voice page composition

### Global shell

Persistent navigation: Home, Create, My Voice, My Music, Studio, Vocal Tools, Harmonies, Songwriting, Mastering, Projects, Library, Export / Release.

My Voice is highlighted.

Top area: Auralis wordmark, global search, settings, user control, and desktop window controls when applicable.

Compact system indicator: Local Mode • Private • Offline.

Keep technical implementation details out of the primary surface; expose them in advanced areas.

### Selected Voice hero

This is the most important visual area.

Left: large voice avatar/art, voice name, version badge, READY/PROCESSING/OFFLINE state, voice description, genre/character tags.

Primary actions: Switch Voice, Train / Improve, Voice Settings.

Right: large animated waveform, training duration, pitch range, model type, sample rate, and voice blend/style controls where actually supported.

The hero must immediately answer: Which voice am I using? Is it ready? What does it sound like? What can I do next?

### Input / Output workbench

Desktop uses a balanced two-column composition.

INPUT tabs: Audio Input, Song Input, Record, My Music.

Large drop zone: Add or drop audio files here.

Secondary actions: Record from Microphone, supported link/audio import, Demo Song/sample.

Recent Inputs show artwork/thumbnail, title, duration, compact waveform, play, and overflow.

OUTPUT tabs: Converted Vocals, Full Songs, Harmonies, Stems. Include History.

Each output card should show artwork, title, voice/version, duration, timestamp, waveform, play, favorite, A/B, download, and overflow.

Output should feel like a premium result library, not a filesystem listing.

### Voice Tools strip

Full-width large tool cards: Voice Conversion, Vocal Doubles, Harmonies, Ad-libs, Pitch & Key, Style Transfer.

Each card gets an icon, short name, one-line explanation, and clear active/disabled state.

Use existing Auralis capabilities. Do not invent backend features merely to match the mockup.

### System status

Small status area may show Voice Models, GPU, and Storage with friendly states such as Voice Models • Ready.

Advanced implementation details remain in Studio → Advanced / Engines.

## 5. Training / improvement experience

Training should feel like creating an instrument.

Use language such as Train Voice, Improve Voice, Add More Takes, Coverage, Vocal Range, Dataset Quality, Model Version.

Keep the existing consent-confirmed capture flow.

Make existing measurements visually understandable: clean signal, room noise, clipping, singing duration, pitch/range coverage, take count, training minutes.

Example status: Your voice is strong / 42 min recorded / Range C2–C5 / Coverage 86% / 2 more low-register takes recommended.

Do not expose raw ML implementation concepts unless the user opens an advanced view.

## 6. Interaction principles

Every screen should have one obvious primary action and a small number of secondary actions. Advanced controls should appear when needed.

Audio is visual: wherever a result exists, use waveform, playhead, duration, A/B comparison, and processing state rather than plain filenames alone.

Long jobs must visibly communicate queued, analyzing, converting, finishing, complete, or failed. Never imply completion before the backend confirms it.

Motion should be subtle: waveform movement, soft active glow, progress transitions, panel expansion, and hover lift. Respect reduced-motion preferences.

## 7. Architecture constraints

This is a UI redesign, not an Auralis rewrite.

Preserve the existing FastAPI APIs, voice store, Seed-VC integration, model lifecycle/registry, conversion queue, history, My Music integration, My Voice capture/training, full-song pipeline, vocal production, mastering, local-first architecture, tests, and Studio → Advanced engine controls.

Reuse existing components where sensible. Refactor only when it clearly reduces duplication or enables the new design.

Do not create a second voice state store or a second backend pathway just for the new UI.

## 8. Design-system implementation

Establish reusable primitives for the shell, cards, buttons, tabs, badges, waveform, status, tool cards, audio rows, and voice hero.

Names can follow existing project conventions. Prefer existing theme.css and shared UI primitives over one-off styles.

My Voice is the reference consumer of the design system.

## 9. Responsive behavior

Desktop is the primary target because Auralis is a local workstation application.

Also support practical laptop widths, tablet, and narrow browser windows.

At narrower widths, collapse the hero gracefully, stack input/output, wrap tool cards, and allow navigation to collapse. Avoid normal-workflow horizontal scrolling.

## 10. Product differentiation

The UI should communicate the strongest existing Auralis differentiators: local-first privacy, trained personal voices, original song workflow, demo-to-song, Artist DNA, vocal production, mastering, editable stems/projects, and model/hardware awareness.

Do not put every capability on the first screen.

First impression: I can make music with my voice here.
Deeper impression: this is an entire local music studio.

## 11. Open-source / community-readiness

The product should be screenshot-friendly and demo-friendly.

A GitHub visitor should understand the product quickly from the README, one hero screenshot, one short demo, and a clear local/privacy statement.

Do not claim popularity, star counts, performance, or commercial success that has not been measured.

Future community surfaces may include themes, voice/model adapters, provider plugins, workflows, presets, community components, and reproducible projects.

## 12. Definition of done for first UI pass

- My Voice visibly follows the approved luxury direction.
- Selected voice is immediately understandable.
- Input and output are visually balanced.
- Existing voice conversion works through the redesigned UI.
- Existing training/capture workflows remain functional.
- Existing history remains functional.
- Existing My Music conversion remains functional.
- Existing tests remain green.
- Frontend build succeeds.
- No fake controls imply unsupported backend capabilities.
- No existing feature is silently removed.
- UI is responsive at practical desktop widths.
- Design can be reused on other Auralis pages without copying large blocks of CSS.

## 13. Product sequence

1. My Voice luxury redesign.
2. Extract reusable Auralis design primitives.
3. Apply shell/navigation polish.
4. Bring Create into the same visual language.
5. Bring My Music / Projects into the same visual language.
6. Polish Studio and advanced controls.
7. Polish Release / Export.
8. Upgrade README screenshots and demo presentation.

My Voice is the visual proving ground.

## 14. Owner direction

The owner approved the generated Auralis luxury mockup on 2026-09-30.

Central composition: premium dark studio shell → selected voice hero → input/output workbench → voice tools → local system status.

Implementation should reproduce the design intent and hierarchy, not copy the image literally and not imitate Kits or Suno pixel-for-pixel.

Core message: your music stays on your machine.
## 15. Implementation status (Session 020)

- **Built:** My Voice in this direction (`frontend/src/VoicePage.jsx`, `VoicePage.css`) on a reusable layer (`frontend/src/Lux.jsx`, `lux.css`). See `AURALIS_CURRENT_ARCHITECTURE.md` for what each part does.
- **Not built, on purpose (no backend capability yet):** Song Input (full-mix separation, V5), link import, Demo Song sample, voice blend/style controls, Style Transfer, a Storage status, a model version number (the hero shows the real training steps instead), Full Songs / Harmonies / Stems output tabs (those results live in Create and Projects, linked from Output).
- **Not changed yet:** the global shell (sidebar, gold wordmark, player bar) and the other pages. They are the next steps of §13, after the owner validates My Voice.
