"""Word guide singer (Session 025, EXPERIMENTAL): sings the lyrics' actual words.

The built-in vocalise guide sings vowels only (Session 024: 0/7 words
recognised). This guide makes words the smallest way that works locally, with
no singing model:

1. **Speech.** Each lyric word is spoken once by a local text-to-speech voice
   (Windows SAPI, built in; nothing is downloaded).
2. **Analysis.** The spoken word is cut into short frames, each described by its
   vocal-tract envelope (LPC), loudness and whether it is voiced. Multi-
   syllable words are split at the loudness dips between their vowel nuclei.
3. **Singing.** Every syllable is laid on its note: consonants keep their own
   timing (the onset lands just *before* the note, as singers do), only the
   steady part of the vowel is stretched, and voiced frames are re-excited by a
   glottal source at the score's exact pitch (glide and vibrato as in the
   vocalise guide). Unvoiced frames (s, t, k, h, ...) keep their original
   noise, so consonants stay crisp.

The result is a dry, clearly worded but plain guide; Seed-VC then makes it the
user's voice, as with the vocalise guide. Measured in Session 025; see
AURALIS_SESSION.md for intelligibility and pitch numbers.

LICENCE NOTE: the words come from Windows speech voices. Until their terms for
distributing generated audio are reviewed, songs sung from this guide are for
the owner's personal, local use, not commercial release. The provider says so
in its status and every song it sings records it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import numpy as np

SR = 44100
WORK_SR = 22050
FRAME = 512                       # 23 ms at 22.05 kHz
HOP = 128                         # 75 % overlap
LPC_ORDER = 24
ONSET_LEAD_MAX = 0.12             # seconds a consonant may start before its note
TRANSITION = 0.035                # seconds of the vowel kept unstretched at each end
LICENCE_NOTE = ("Experimental. Words are spoken by a Windows speech voice: personal, local use only "
                "until the voice's licence for distributing generated audio is reviewed.")


# ── text-to-speech (Windows SAPI) ─────────────────────────────────────────

def available_voices() -> list[str]:
    if sys.platform != "win32":
        return []
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                              timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def speak_words(words: list[str], folder: str, voice: str = "Microsoft Zira Desktop", rate: int = -1) -> dict:
    """Speak each distinct word into its own WAV (one PowerShell call). word → path."""
    unique = sorted({w for w in words if w})
    paths = {w: os.path.join(folder, f"w{i:04d}.wav") for i, w in enumerate(unique)}
    if not unique:
        return {}
    lines = ["Add-Type -AssemblyName System.Speech",
             "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
             f"try {{ $s.SelectVoice('{voice}') }} catch {{ }}",
             f"$s.Rate = {int(rate)}"]
    for w, p in paths.items():
        safe = w.replace("'", "''")
        lines += [f"$s.SetOutputToWaveFile('{p}')", f"$s.Speak('{safe}')"]
    lines += ["$s.SetOutputToNull()", "$s.Dispose()"]
    script_path = os.path.join(folder, "speak.ps1")
    with open(script_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
                          capture_output=True, text=True, timeout=60 + 5 * len(unique),
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    missing = [w for w, p in paths.items() if not os.path.exists(p)]
    if done.returncode != 0 or missing:
        raise RuntimeError(f"Windows speech could not say {len(missing)} word(s): {(done.stderr or '')[-400:]}")
    return paths


# Words a speech voice says in their dictionary (strong) form when spoken alone,
# while singers use the weak form: "the" alone is "thee" (heard as "they"), "a"
# alone is "ay". Respelled for the speech engine only; the lyrics are unchanged.
def tts_text(word: str, next_word: str = "") -> str:
    if word == "the":
        return "thee" if next_word[:1] in tuple("aeiou") else "thuh"
    if word == "a":
        return "uh"
    return word


# ── analysis ──────────────────────────────────────────────────────────────

class Word:
    """A spoken word as frames: LPC envelope, gain, voicing, residual."""

    def __init__(self, audio: np.ndarray, sr: int = WORK_SR):
        import librosa
        from scipy.signal import lfilter

        y, _ = librosa.effects.trim(audio.astype(np.float64), top_db=38)
        if len(y) < FRAME * 2:
            y = np.pad(y, (0, FRAME * 2 - len(y)))
        self.y = y
        pad = np.pad(y, (FRAME // 2, FRAME))
        win = np.hanning(FRAME)
        n_frames = 1 + (len(pad) - FRAME) // HOP
        self.lpc = np.zeros((n_frames, LPC_ORDER + 1))
        self.rms = np.zeros(n_frames)
        self.residual = np.zeros((n_frames, FRAME))
        rng = np.random.default_rng(len(y))
        for k in range(n_frames):
            fr = pad[k * HOP:k * HOP + FRAME] * win
            self.rms[k] = float(np.sqrt(np.mean(fr ** 2)))
            a = librosa.lpc(fr + 1e-6 * rng.standard_normal(FRAME), order=LPC_ORDER)
            a = a if np.all(np.isfinite(a)) else np.r_[1.0, np.zeros(LPC_ORDER)]
            self.lpc[k] = a
            self.residual[k] = lfilter(a, [1.0], fr)
        f0, voiced, prob = librosa.pyin(pad, fmin=70, fmax=500, sr=sr, frame_length=FRAME * 2, hop_length=HOP,
                                        center=False)
        v = np.zeros(n_frames, bool)
        m = min(n_frames, len(voiced))
        v[:m] = voiced[:m] & (prob[:m] > 0.3)
        # pyin's voicing is unreliable on short isolated words (its first frames of "take", "my"
        # came out unvoiced and kept the speech pitch). A frame is also voiced when it is clearly
        # periodic in the voice's range (normalised autocorrelation) and not quiet.
        lo_lag, hi_lag = int(sr / 500), int(sr / 70)
        periodic = np.zeros(n_frames)
        for k in range(n_frames):
            fr = pad[k * HOP:k * HOP + FRAME]
            fr = fr - fr.mean()
            ac = np.correlate(fr, fr, "full")[FRAME - 1:]
            if ac[0] > 1e-12:
                periodic[k] = float(np.max(ac[lo_lag:min(hi_lag, FRAME - 1)]) / ac[0])
        loud = self.rms > 0.06 * (self.rms.max() or 1)
        v |= loud & (periodic > 0.5)
        self.voiced = v

    def syllables(self, count: int) -> list[tuple[int, int]]:
        """Split the frames into `count` syllables at the loudness dips between vowel nuclei."""
        n = len(self.rms)
        if count <= 1:
            return [(0, n)]
        energy = np.convolve(self.rms * self.voiced, np.ones(5) / 5, "same")
        idx = np.flatnonzero(self.voiced)
        if len(idx) < count * 3:
            edges = np.linspace(0, n, count + 1).astype(int)
            return [(int(a), int(b)) for a, b in zip(edges, edges[1:])]
        lo, hi = idx[0], idx[-1] + 1
        # candidate dips: local minima of voiced energy, deepest first, at least 4 frames apart
        cand = [k for k in range(lo + 3, hi - 3) if energy[k] <= energy[k - 1] and energy[k] <= energy[k + 1]]
        cand.sort(key=lambda k: energy[k])
        cuts = []
        for k in cand:
            if all(abs(k - c) >= 6 for c in cuts):
                cuts.append(k)
            if len(cuts) == count - 1:
                break
        if len(cuts) < count - 1:
            edges = np.linspace(lo, hi, count + 1).astype(int)
            cuts = list(edges[1:-1])
        edges = [0] + sorted(int(c) for c in cuts) + [n]
        return list(zip(edges, edges[1:]))


# ── synthesis ─────────────────────────────────────────────────────────────

def _plan(word: Word, seg: tuple[int, int], frames_out: int, lead: int) -> list[int]:
    """Source frame for each output frame of one syllable: the consonant onset
    (`lead` frames) and transitions play at speed, the steady vowel is stretched."""
    a, b = seg
    src = list(range(a, b))
    voiced = [k for k in src if word.voiced[k]]
    if not voiced or frames_out <= len(src):
        # nothing to stretch, or the note is shorter than the spoken syllable: resample evenly
        return [src[min(len(src) - 1, int(i * len(src) / max(1, frames_out)))] for i in range(frames_out)]
    keep = int(TRANSITION * WORK_SR / HOP)
    v0, v1 = voiced[0], voiced[-1] + 1
    s0, s1 = min(v1, v0 + keep), max(v0 + keep, v1 - keep)        # steady part of the vowel
    if s1 - s0 < 2:
        s0, s1 = v0, v1
    head, steady, tail = list(range(a, s0)), list(range(s0, s1)), list(range(s1, b))
    room = frames_out - len(head) - len(tail)
    if room < len(steady):
        return [src[min(len(src) - 1, int(i * len(src) / frames_out))] for i in range(frames_out)]
    stretched = [steady[min(len(steady) - 1, int(i * len(steady) / room))] for i in range(room)]
    return head + stretched + tail


class WordSinger:
    """Score (GuideNotes with syllables and their words) → dry mono guide at 44.1 kHz."""

    def __init__(self, voice: str = "Microsoft Zira Desktop"):
        self.voice = voice

    def sing(self, score, total_seconds: float, seed: int = 0) -> np.ndarray:
        import librosa
        from scipy.signal import lfilter

        rng = np.random.default_rng(seed + 71)
        n_out = int((total_seconds + 1.0) * WORK_SR)
        if not score:
            return np.zeros(int((total_seconds + 1.0) * SR), np.float32)

        # group notes into words: (word text, [note indices])
        groups = []
        for i, note in enumerate(score):
            text = getattr(note, "word", "") or note.syllable
            pos = getattr(note, "word_pos", 0)
            if groups and pos > 0 and groups[-1][0] == text:
                groups[-1][1].append(i)
            else:
                groups.append((text, [i]))
        # what the speech engine says for each word, given the word after it (weak forms)
        say = [tts_text(text, groups[gi + 1][0] if gi + 1 < len(groups) else "") for gi, (text, _) in enumerate(groups)]
        with tempfile.TemporaryDirectory(prefix="auralis_words_") as folder:
            paths = speak_words([t for t in say if t], folder, voice=self.voice)
            spoken = {t: Word(librosa.load(p, sr=WORK_SR)[0]) for t, p in paths.items()}

        # per output frame: source word/frame, target midi, velocity, phrase membership
        n_frames = n_out // HOP + 2
        src_ref = [None] * n_frames                       # (Word, frame index)
        target = np.full(n_frames, np.nan)
        vel = np.zeros(n_frames)
        for (text, idxs), said in zip(groups, say):
            if not said or said not in spoken:
                continue
            word = spoken[said]
            segs = word.syllables(len(idxs))
            for note_i, seg in zip(idxs, segs):
                note = score[note_i]
                start_f = int(round(note.start * WORK_SR / HOP))
                end_f = int(round((note.start + note.duration) * WORK_SR / HOP))
                # onset consonant: the unvoiced frames before the syllable's first voiced frame
                first_v = next((k for k in range(*seg) if word.voiced[k]), seg[0])
                lead = min(first_v - seg[0], int(ONSET_LEAD_MAX * WORK_SR / HOP))
                begin = max(0, start_f - lead)
                frames = _plan(word, seg, max(1, end_f - begin), lead)
                for j, k in enumerate(frames):
                    f = begin + j
                    if f >= n_frames:
                        break
                    src_ref[f] = (word, k)
                    target[f] = note.midi
                    vel[f] = note.velocity / 127

        # pitch contour: hold each note, glide 40 ms between notes, vibrato on long notes
        midi = target.copy()
        known = np.flatnonzero(np.isfinite(midi))
        if len(known):
            midi = np.interp(np.arange(n_frames), known, midi[known])
        glide = max(1, int(0.04 * WORK_SR / HOP))
        midi = np.convolve(np.pad(midi, (glide // 2, glide - glide // 2 - 1), mode="edge"), np.ones(glide) / glide, "valid")
        vib = np.zeros(n_frames)
        for note in score:
            if note.duration > 0.35:
                a = int((note.start + 0.15) * WORK_SR / HOP)
                b = min(n_frames, int((note.start + note.duration) * WORK_SR / HOP))
                tt = np.arange(max(0, b - a)) * HOP / WORK_SR
                vib[a:b] = 0.28 * np.sin(2 * np.pi * 5.4 * tt) * np.clip(tt / 0.25, 0, 1)
        f0_frames = 440.0 * 2 ** ((midi + vib - 69) / 12)
        f0 = np.interp(np.arange(n_frames * HOP) / HOP, np.arange(n_frames), f0_frames)
        phase = 2 * np.pi * np.cumsum(f0) / WORK_SR
        n_h = int(min(40, (WORK_SR / 2 - 500) / max(60.0, float(np.nanmin(f0)))))
        glottal = sum(np.sin(h * phase) / h ** 1.2 * (f0 * h < WORK_SR / 2 - 400) for h in range(1, n_h + 1))
        glottal = glottal + 0.015 * rng.standard_normal(len(glottal))        # a little breath

        # overlap-add: each frame's excitation through its source frame's envelope, at its loudness
        out = np.zeros(n_frames * HOP + FRAME)
        norm = np.zeros_like(out)
        win = np.hanning(FRAME)
        for f, ref in enumerate(src_ref):
            if ref is None:
                continue
            word, k = ref
            s = f * HOP
            if word.voiced[k]:
                exc = glottal[s:s + FRAME]
                if len(exc) < FRAME:
                    continue
                exc = exc * win
            else:
                exc = word.residual[k]
            seg = lfilter([1.0], word.lpc[k], exc)
            r = float(np.sqrt(np.mean((seg * win) ** 2)))
            if r > 1e-9:
                seg = seg * (word.rms[k] / r) * (0.55 + 0.45 * vel[f])
            out[s:s + FRAME] += seg * win
            norm[s:s + FRAME] += win ** 2
        out = out[:n_out] / np.maximum(norm[:n_out], 1e-3)
        out = librosa.resample(out, orig_sr=WORK_SR, target_sr=SR)
        sung = np.abs(out) > 1e-4
        rms = float(np.sqrt(np.mean(out[sung] ** 2))) if sung.any() else 1.0
        gain = min(10 ** (-20 / 20) / max(rms, 1e-9), 10 ** (-3 / 20) / max(float(np.abs(out).max()), 1e-9))
        result = np.zeros(int((total_seconds + 1.0) * SR), np.float32)
        result[:min(len(result), len(out))] = (out * gain)[:len(result)]
        # notes with no words (ad-libs, wordless sections) are vocalised, as before
        wordless = [n for n in score if not (getattr(n, "word", "") or n.syllable)]
        if wordless:
            from .singing_provider import VocaliseSinger

            hum = VocaliseSinger().sing(wordless, total_seconds, seed=seed)
            n = min(len(result), len(hum))
            result[:n] += hum[:n]
            peak = float(np.abs(result).max())
            if peak > 10 ** (-3 / 20):
                result *= 10 ** (-3 / 20) / peak
        return result
