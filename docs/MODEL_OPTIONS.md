# Model options for the remaining phases

**Added:** 2026-09-25 (Session 016). **Status:** research only. Nothing has been downloaded or installed.

Three remaining features need a local model that Auralis doesn't ship. Each would be installed like Seed-VC:
- in its own folder and virtual environment under `%LOCALAPPDATA%\Auralis\providers\`
- behind an existing provider boundary
- never inside the MIT package

This page records what was found, so the choice can be made once. Licences change; re-check each model's official page before installing. This is an engineering summary, not legal advice.

## Summary

| Feature | Candidate | Code licence | Weights / voice licence | Commercial use of results | Hardware |
|---|---|---|---|---|---|
| **AU-11** generative audio behind `generation.PROVIDERS` | **ACE-Step** (v1 3.5B, 1.5) | Apache-2.0 | Apache-2.0 | Yes | Around 8 GB VRAM for practical use; 12 GB+ recommended; XL variants need offload/quantization on 12 GB |
| | MusicGen (Audiocraft) | MIT | **CC-BY-NC 4.0** | **No** | Similar |
| | Stable Audio Open | — | Stability AI Community Licence | Only under US$1M annual revenue | Similar |
| **V5** full-song vocal separation | Demucs / HTDemucs | MIT | **Scientific use only** (per the maintainer; no new grant for v4) | **No** for the pretrained weights | Runs on CPU (slow) or GPU |
| **Words** for the guide singer (`voice.singing_provider`) | DiffSinger (openvpi) + OpenUtau | Apache-2.0 | Per voicebank: the English voices found (e.g. TIGER, Peiton) are **non-commercial** unless a licence is bought | Only with a purchased voicebank licence | GPU helps; moderate |

## What each would add

- **ACE-Step (AU-11).** A `GenerativeRenderer` behind the same render contract as the synth, for richer textures or whole sections from the blueprint (tempo, key, section prompt).
  - This is the only candidate whose weights allow commercial use outright.
  - Its VRAM need competes with Seed-VC on the RTX 4070 (12 GB), so the two must never be loaded at once. The engine lock and a model scheduler (roadmap §16) are prerequisites.
  - It can also generate vocals, but Auralis would keep the user's own voice path for those.
- **Separation (V5).**
  - The obvious model (Demucs) is non-commercial for its weights.
  - A separation model with commercially clear weights still needs to be found before V5 can be recommended for released music.
  - For personal or non-commercial use, Demucs would work.
- **Words.** DiffSinger with an English voicebank would replace the vocalise guide. The guide is converted into the user's voice by Seed-VC anyway, so the voicebank's timbre never reaches the final record. Its licence still governs its use as a guide.

## Recommendation

1. **Words first**, if releasing music is the goal: buy (or find) an English DiffSinger voicebank licence that allows commercial use. It is the biggest quality jump, because the lyrics become intelligible.
2. **AU-11 with ACE-Step** only after a model scheduler exists (unload Seed-VC before loading ACE-Step). It is licence-clean.
3. **V5:** defer until a separation model with commercially usable weights is identified. For personal use, Demucs is fine.

Sources: [ACE-Step](https://github.com/ace-step/ACE-Step), [ACE-Step on Hugging Face](https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B), [Spheron guide to open music models (2026)](https://www.spheron.network/blog/deploy-open-source-ai-music-generation-gpu-cloud-2026/), [Demucs](https://github.com/facebookresearch/demucs), [Demucs weights licence discussion](https://github.com/ContextualWisdomLab/bandscope/issues/1181), [DiffSinger](https://github.com/openvpi/DiffSinger), [TIGER voicebank](https://github.com/spicytigermeat/tiger_diffsinger), [Peiton commercial licence](https://nebm.gumroad.com/l/vvhyg).
