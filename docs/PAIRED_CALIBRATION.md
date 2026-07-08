# Paired Studio Calibration

Paired Calibration accepts:

1. a guide vocal from a generated or produced song; and
2. the musician singing the same words, melody, and phrasing.

It is not enough for the two files to share a title. Auralis compares chroma,
timing slope, and local phrase similarity. Mismatched arrangements are rejected.
For a valid pair, Auralis preserves high-confidence 12-second guide/target clips
and adds only the real singer's verified phrases to the voice dataset.

## Why paired examples help

Unpaired recordings teach vocal identity across a range of material. Paired
examples provide a controlled evaluation: the melody and words are nearly fixed,
so changes in speaker similarity can be measured more meaningfully.

Paired material should not automatically receive unlimited training weight.
Over-repeating one song can make a model inherit source artifacts or overfit one
register. Auralis therefore stores pairs separately, reports usable aligned
seconds, and permits developers to treat them as calibration, validation, or
carefully weighted supervised data.

## Recommended files

```text
Song Name/
  guide_vocal.wav
  my_matching_dry_vocal.wav
  instrumental.wav        # optional but useful
```

Both vocals should be isolated. The singer target should be dry and should not
contain the guide vocal, reverb tail, or the mastered instrumental.

## Future training work

The current Seed-VC fine-tune learns primarily from the singer targets. A future
paired trainer should add:

- phoneme- and note-aligned content losses;
- speaker-embedding loss toward the real singer;
- adversarial penalties against guide-voice leakage;
- multi-resolution spectral and transient reconstruction losses;
- held-out-song early stopping;
- balanced sampling by vowel, register, articulation, and song;
- automatic checkpoint selection based on multiple identity and quality metrics.

No single speaker-similarity score should select a production model by itself.
Listening tests, intelligibility, source leakage, pitch accuracy, and held-out
material all matter.
