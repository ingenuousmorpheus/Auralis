# Pitch Polish

Pitch Polish is Auralis' beginner-safe automatic vocal tuning stage. It does
not load or control Auto-Tune or Melodyne; it implements an original local
workflow inspired by the professional concepts those tools expose.

## One-Click Studio Polish

After voice conversion, one button performs:

1. key detection from the instrumental, or from the vocal when no instrumental
   is supplied;
2. monophonic note and confidence detection;
3. scale-aware melody mapping with contour preservation;
4. pitch-center correction that leaves vibrato and slides intact;
5. preservation of high-frequency consonants, sibilants, and breaths;
6. Vocal Finish tone, dynamics, de-essing, depth, and mix placement.

The instrumental is strongly recommended. A naked vocal often does not contain
enough harmonic context to distinguish related keys reliably.

## Correction characters

- **Natural:** rescues clear misses while leaving close notes and expression
  mostly untouched.
- **Studio:** polished contemporary correction without obvious hard tuning.
- **Modern:** tighter centers and faster-sounding correction.
- **Hard Tune:** deliberate scale snapping for an audible effect.

Low-confidence notes receive restrained correction. Every detected note is
written to a JSON report with its original center, target note, confidence, raw
error, and applied correction.

## Musical limits

Automatic tuning cannot know an unwritten melody with certainty. A note outside
the detected scale may be an intentional borrowed tone, blue note, passing tone,
or detection error. The contour-aware mapper reduces bad choices, but future
versions should add:

- an editable piano-roll/blob view;
- chord-track analysis rather than one global key;
- lyric/phoneme boundaries and explicit note separations;
- independent slow pitch-drift control;
- MIDI melody or reference-vocal guidance;
- per-note bypass, target selection, and correction strength;
- formant-aware time and pitch algorithms for larger corrections.

The automatic mode is intended to produce a strong first pass. The report and
future note editor preserve the musician's final say.
