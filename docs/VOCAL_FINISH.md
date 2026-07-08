# Vocal Finish

Vocal Finish is Auralis' post-conversion production stage. It is designed around
two practical observations:

1. A vocal must be judged inside the instrumental, not only in solo.
2. Two gentle compression stages usually sound more natural than forcing one
   compressor to perform leveling and peak control simultaneously.

## Automatic analysis

For every converted vocal, Auralis measures:

- integrated loudness and true peak;
- crest factor and active dynamic range;
- rumble, low-mid buildup, presence, and sibilance energy;
- when an instrumental is supplied, vocal-to-instrument loudness and spectral
  overlap.

Those measurements generate an inspectable processing decision rather than a
fixed preset. The JSON report records every parameter and the reason it changed.

## Processing stages

1. Adaptive high-pass cleanup.
2. Low-mid pocket EQ.
3. Presence and air shaping.
4. Dynamic sibilance reduction.
5. Slow leveling compression.
6. Faster peak compression.
7. Gentle harmonic density.
8. Optional stereo double and short ambience sends.
9. Mix-context level and center-pocket adjustment.
10. True-peak-safe 24-bit export.

Five characters are included: Natural Cleanup, Polished Pop, Smooth R&B,
Intimate Detail, and Forward & Dense. Intensity continuously scales the finish.

## Future developer extensions

The architecture intentionally leaves room for:

- key-aware note correction with editable pitch nodes and protected vibrato;
- beat-grid-aware consonant and phrase timing, with groove-strength controls;
- automatic vocal comping from multiple takes;
- plosive, click, mouth-noise, and spectral-repair modules;
- lyric/phoneme alignment for surgical consonant editing;
- learned breath control that never removes intentional emotional breaths;
- section-aware automation so verses, pre-choruses, and hooks receive different
  density and ambience;
- automatic lead doubles, harmonies, ad-libs, and backing-vocal placement;
- reference-vocal matching for tone, depth, and dynamic behavior;
- an editable decision timeline where every automatic edit can be auditioned,
  bypassed, moved, or resized;
- DAW interchange through AAF, MIDI automation, and rendered effect stems;
- profile-specific finish calibration learned from the musician's approved
  edits, without uploading their voice or sessions.

The product principle is “fast first draft, professional reversibility.” Future
automation should expose what it changed and preserve a clean undo path.
