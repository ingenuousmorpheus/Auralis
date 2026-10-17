# Plugin Intelligence — Phase 1

Implemented 2026-10-16 in the existing FastAPI/React application. No third-party plugin hosting or audio processing was added. Personal voice capture, training, cloning, word-guide defaults and all existing DSP paths are unchanged.

## Use

Open **Studio → Plugin Library** (also listed under sidebar Tools). Click **Scan plugin folders**. Add only dedicated plugin directories, one absolute path per line, for installations outside the standard locations. Search names, manufacturers or functions; choose a category. Select one of five vocal styles and **Suggest a chain**.

The inventory and additional roots are session-only, in backend memory. Restarting the backend clears the inventory. No paid service is used. Search is deterministic text matching, not a conversational AI. The API exposes `POST /plugins/scan` (`paths` adds roots), `GET /plugins?query=&category=`, and `GET /plugins/chains?template=`.

## Discovery and trust

- Fixed Windows roots: VST3/VST2 Common Files, VstPlugins and Steinberg/VstPlugins under the available Program Files variants; per-user LocalAppData/Programs/Common/VST3. Custom roots supplement these. Mixcraft-specific folders are not inferred from the registry or its private configuration.
- Read directory entries, bounded PE headers and Windows version resources only. The system `version` library reads CompanyName/FileVersion; it never loads the plugin as code. File resource metadata is self-reported, not an authenticity check.
- Bundled VST3: bounded (1 MiB) Contents/Resources/moduleinfo.json reads (legacy Contents/moduleinfo.json fallback), audio module classes separated, class IDs retained. Single-file VST3: format candidate from extension + PE architecture. DLLs always remain **VST2 candidates**; no assertion that an arbitrary DLL is a plugin.
- No LoadLibrary on plugin files, plugin instantiation, registry access, subprocesses, DAW actions, activation or binary writes. Ignore other file contents. Reparse points/symlinks, network roots, drive roots and obvious broad/private roots are rejected. Traversal is capped at 20,000 entries. Missing, inaccessible, invalid and capped locations remain visible.
- Catalog file paths are local UI details; never written to logs or persisted. Diagnostic locations use indices. Only allowlisted metadata fields are returned; arbitrary activation/license fields are ignored. User-selected paths must still be dedicated plugin roots; this is not a whole-drive scanner. A malicious filesystem changing links during a scan is outside this passive local-tool threat model.
- Unknown vendor, version, category and architecture remain Unknown. No plugin loading means shells (notably Waves), absent moduleinfo, unusual layouts and subplugins cannot always be resolved. No Waves/Soundtoys ownership or absence is inferred from this scan.
- Duplicate groups are **possible** duplicates: shared VST3 class ID, otherwise case-insensitive vendor + name. Byte identity and VST2/VST3 equivalence are not claimed. Unknown manufacturers increase false matches. All installations stay visible.

## Classification and vocal planning

Transparent product-name rules and VST3-declared subcategories, with evidence per entry. Vendor names alone never imply functions. Categories support all requested vocal functions, instruments and unknown; one entry can have multiple functions. Rules cover a small identifiable subset; unknown does not mean incapable.

Five templates: Clean natural lead, Modern pop/R&B lead, Doubles and harmonies, Smooth melodic vocal, Creative atmospheric vocal. Each step gives its purpose and either an inventory ID or **Unavailable or unverified**. Missing means not identified in this catalog, not proof the owner lacks a license.

Selection is deterministic alphabetical order among classified x64 VST3 file candidates/metadata declarations, not a quality ranking. VST2 candidates, x86, unknown architecture and invalid metadata are excluded from recommendations. VST3 candidates still need owner/host validation, and recommendations cannot prove licensing, host compatibility or successful audio processing. Reverb/delay may be sends; cleanup and tuning are conditional on the recording. Future AI explanations can consume these records and evidence without changing scanner trust boundaries.

## Mixcraft 10 research (2026-10-16)

1. **Discovery:** Mixcraft preferences document VST/VST3 startup loading, editable VST folder lists, rescanning, and Plugin Manager enable/disable/collections. Auralis does not read or alter these settings. [Acoustica preferences](https://acoustica.com/mixcraft-10-manual/preferences)
2. **Supported automation exists:** JavaScript **control-surface** scripting with MIDI/SysEx and an integrated script editor is documented. This is a candidate for supported transport/mixer workflows. An external general-purpose RPC interface, arbitrary plugin insertion/preset automation, and an offline host API have not been established by this research. Do not equate controller scripting with a complete external engineering agent. [Acoustica controller API](https://acoustica.com/mixcraft-10-manual/the-mixcraft-10-controller-script-api), [official API documentation](https://acousticainc.github.io/controller-script-api-docs/docs/intro/)
3. **VocAlign:** The local candidates are named VocALignPro / VocALignProP, both x86; version/edition and operational compatibility remain unknown. Project 5 documentation describes ARA and separate realtime VST3/AU capture, the latter requiring sidechain routing. That documentation cannot establish the installed older Pro edition's capabilities. No generic ARA compatibility claim for Mixcraft is made. A supported host/bridge and edition-specific capture workflow must be checked manually on copies of stems. [Synchro Arts edition/host notes](https://www.synchroarts.com/manuals/VocAlignProjectV5/Manual/HTML/vocalign-project-5-plug-in-versions-and-daws.html)
4. **Antares:** x64 VST3 candidates are structurally plausible for Mixcraft's documented VST3 support, not verified hosted instances. Antares requires matching plugin edition, OS/DAW compatibility and applicable activation. File presence does not prove an active license. This phase did not inspect activation state. [Antares discovery guidance](https://help.antarestech.com/hc/en-us/articles/41074554554260-Why-is-my-Antares-plug-in-not-showing-up-in-my-DAW)
5. **REA:** Assessed the installed reverse-engineer-anything skill and exposed REA tool inventory. Those describe binary/package inspection and selected runtime/browser instrumentation; they do not establish a supported Mixcraft desktop-control adapter or audio engine. No target opened, debugged, hooked or executed. REA might help future read-only artifact investigation if a concrete unsupported integration question warrants it; prefer documented Mixcraft controls first. Native desktop automation remains unverified and out of Phase 1.

Product-rule references: [Antares vocal mixing functions](https://www.antarestech.com/products/vocal-mixing), [SoundSoap](https://help.antarestech.com/hc/en-us/articles/41115415879828-Auto-Tune-SoundSoap-FAQ), [Vocal Reverb](https://www.antarestech.com/documentation/vocal-reverb), [FabFilter Pro-Q 2](https://prod.fabfilter.com/press/1409212800/fabfilter-releases-fabfilter-pro-q-2-equalizer-plug-in), [Softube CL 1B](https://www.softube.com/eu/user-manuals/tube-tech-cl-1b-and-cl-1b-mk-ii-compressors).

## Verification and next gate

Synthetic fixtures exercise formats, unknowns, malformed metadata, multiple functions, duplicate groups, missing directories, architecture, overlap, caps, private roots, reparse exclusions, secret-field filtering, read-only behavior, no subprocess/DLL execution, quiet logs, API routes and inventory-only chains. Build and regression results are recorded in the session files.

No real Mixcraft hosting, routing, preset, listening, activation or ARA check was performed. UI runtime/visual behavior has not yet been manually validated. The build and API tests do not substitute for those checks. Full expensive speech-recognition suite was not rerun for this isolated catalog addition.

Stop after Phase 1. Safest next step: owner reviews discovered entries and supplies any additional dedicated plugin roots, then approves a separate manual compatibility/listening trial on copied stems. Resolve the installed VocAlign edition/architecture and Mixcraft sidechain/bridge requirements before designing alignment automation. Any plugin execution, DAW configuration, automation or installations belong to separately approved work. No push or merge.

## Local discovery verification

The development-machine passive scan found 49 entries (32 VST3 and 17 VST2 candidates), with 40 x64, eight x86 and one unknown architecture. Sixteen entries participated in possible duplicate groups. These numbers describe that local test, not a bundled inventory or a guarantee about another machine. The detailed installed-product inventory is retained locally and excluded from GitHub.

Metadata schema reference: [Steinberg moduleinfo](https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/VST%2BModule%2BArchitecture/ModuleInfo-JSON.html). Sub Categories arrays and legacy pipe-delimited strings are accepted. This implementation uses strict JSON; optional JSON5 comments/trailing commas are conservatively reported as invalid metadata, with no plugin execution fallback.

Final verification: **27 plugin tests passed**, **66 existing voice/model/harmony/engine regressions passed** (11 dependency/short-audio warnings), and **Vite production build passed** (49 modules). No real Mixcraft or UI visual validation was performed. Changes remain local and uncommitted.
