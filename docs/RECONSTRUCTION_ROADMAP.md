# Instrument reconstruction roadmap

Auralis 0.3 is a stem mixer and mastering engine. It does **not** yet convert
arbitrary stems to MIDI or recreate the original instrument. That feature
requires a separate transcription and rendering subsystem; treating it as an
EQ preset would produce unreliable results.

## Target architecture

1. **Stem routing**
   - Detect vocal, drums, bass, monophonic melodic, and polyphonic harmonic
     material.
   - Let the user override every decision.

2. **Expressive transcription**
   - Monophonic sources: note onsets, offsets, pitch contour, vibrato, bends,
     velocity, and confidence.
   - Polyphonic sources: multi-pitch note events with pedal and articulation
     support.
   - Drums: class-specific onset detection with kick, snare, hat, cymbal, tom,
     and percussion mapping.
   - Export standard MIDI plus optional MPE pitch/pressure data.

3. **Instrument identity**
   - Estimate family and playing technique separately from note content.
   - Prefer user-selected, licensed instruments over pretending an automatic
     guess is exact.

4. **Renderer**
   - Render through a local sampler or plugin host.
   - Preserve timing micro-variation and dynamics instead of hard quantizing.
   - Keep the original stem available as a phase-aligned residual layer for
     attacks, noise, room tone, and articulations MIDI cannot represent.

5. **Round-trip optimizer**
   - Compare the render with the source using multi-resolution spectral,
     loudness, onset, pitch, stereo, and transient losses.
   - Optimize MIDI expression and renderer parameters within safe bounds.
   - Report confidence and permit source/render blending when reconstruction is
     not perceptually equivalent.

## Product rule

The quality metric is audible reconstruction fidelity and user control—not
whether a third-party “AI detector” can be fooled. Detector scores are unstable
and should not be marketed as proof of authorship or authenticity.
