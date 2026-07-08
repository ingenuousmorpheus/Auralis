# Auralis My Voice Studio

My Voice Studio performs singing voice conversion: a guide vocalist supplies
the melody, lyrics, timing, vibrato, and phrasing; the local model changes the
vocal timbre toward the selected private voice profile.

## Two profile tiers

- **Instant profile (implemented):** 3–30 seconds of clean solo singing. Uses
  Seed-VC's zero-shot singing mode and requires no training.
- **Studio-trained profile (implemented):** at least 10 minutes, with 30–45
  minutes recommended. Auralis segments long recordings, measures phrase count
  and usable pitch span, and fine-tunes the 44.1 kHz singing model.

The Studio training options are 1,000 steps for the normal pass and 2,500 steps
for a deeper pass. Runs are resumable: choosing the same profile again continues
from the most recent Seed-VC checkpoint. The final checkpoint and config are
copied into the private profile directory and automatically selected during
conversion.

## Recording a strong reference

- Record a single, dry, monophonic voice.
- Do not include harmonies, doubles, instrumental bleed, reverb, delay, or a
  mastered backing track.
- Avoid clipping and heavy pitch correction.
- Include confident sustained vowels, consonants, low notes, high notes,
  chest/mix/head voice, and the vocal textures you expect the model to reproduce.
- Include multiple dynamics and deliveries: intimate, full, breathy, rhythmic,
  legato, vibrato, straight tone, soft attacks, and stronger attacks.
- Use only your own voice or a singer who has explicitly authorized the model.

## Local provider

Seed-VC is installed into:

`%LOCALAPPDATA%\Auralis\providers\seed-vc`

It uses its own Python 3.11 environment and CUDA-enabled PyTorch stack. This is
intentional: model dependencies remain isolated from Auralis' mastering engine.
Seed-VC is an optional GPL-3.0 provider and is not copied into the MIT-licensed
Auralis source tree.

The first conversion downloads model checkpoints from Hugging Face. After the
checkpoints are cached, conversion is local.

## What “full voice” means

The trained checkpoint improves identity, tone, register consistency, and
familiar vocal textures. It does not invent a performance from nothing. The
guide vocal still controls the words, melody, timing, phrasing, vibrato, and
emotion. For the most authentic output, perform the guide in the style you want
the finished vocal to carry.

## Quality settings

- **Fast:** 12 diffusion steps, useful for auditions.
- **Studio:** 35 steps, the normal production setting.
- **Ultra:** 50 steps, slower and useful when difficult consonants or sustained
  notes need another pass.

Pitch shifting changes the guide before timbre conversion. Leave it at zero when
the guide is already in the desired key and register.
