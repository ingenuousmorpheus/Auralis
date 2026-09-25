"""Built-in providers (wrapping what Auralis already has) and the planned ones.

Working today:
* ``SeedVCConverter``   My Voice conversion through the separately installed Seed-VC
                        (a per-call subprocess: it loads and frees its own memory each call)
* ``VocaliseGuide``     the built-in formant guide singer (no install, no words)

Planned (not installed, never auto-downloaded):
* ``ACEStepSections``   generated song sections via ACE-Step (Apache-2.0), as a resident
                        ``SubprocessWorker`` in ``providers/ace-step``
* ``DiffSingerGuide``   a lyric-capable guide singer via DiffSinger + a licensed English
                        voicebank, as a resident worker in ``providers/diffsinger``

The planned adapters are complete on the Auralis side: they know where the
provider would live, how to start it, and what to send. They report
``installed = False`` until someone installs the provider (see
``docs/MODEL_OPTIONS.md``), and the registry falls back to the built-ins.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from .interfaces import ConversionRequest, GuideSinger, SectionGenerator, SectionRequest, SectionResult, VoiceConverter
from .lifecycle import ModelNotInstalledError, ModelSpec
from .worker import SubprocessWorker


def providers_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "providers"


# ── working today ───────────────────────────────────────────────────────────

class SeedVCConverter(VoiceConverter):
    spec = ModelSpec(
        id="seed-vc", kind="voice_converter", name="Seed-VC (My Voice)", licence="GPL-3.0, separate provider",
        heavy=True, resident=False, vram_gb=6.0, commit_gb=9.0, min_commit_gb=6.0,
        notes="Runs as a subprocess per conversion; about 9 GB of commit memory while converting "
              "(measured). Below about 6 GB free it fails with os error 1455 (Session 001).")

    def __init__(self, provider=None):
        self._provider = provider
        self.provider_getter = None          # the API points this at its shared provider instance

    @property
    def provider(self):
        if self.provider_getter is not None:
            return self.provider_getter()
        if self._provider is None:
            from ..voice import SeedVCProvider

            self._provider = SeedVCProvider()
        return self._provider

    def is_installed(self) -> bool:
        status = getattr(self.provider, "status", None)
        return True if status is None else bool(status().installed)

    def convert(self, request: ConversionRequest) -> dict:
        return self.provider.convert(
            source_path=request.source_path, reference_path=request.reference_path,
            output_path=request.output_path, semitone_shift=request.semitone_shift, quality=request.quality,
            checkpoint_path=request.checkpoint_path, config_path=request.config_path, progress=request.progress)


class VocaliseGuide(GuideSinger):
    spec = ModelSpec(id="vocalise", kind="guide_singer", name="Auralis vocalise guide (built in)",
                     licence="MIT (part of Auralis)", heavy=False,
                     notes="Sings melody, lyric rhythm and vowels; not intelligible words.")
    sings_words = False
    languages = ()

    def sing(self, score, total_seconds, seed=0):
        from ..voice.singing_provider import VocaliseSinger

        return VocaliseSinger().sing(score, total_seconds, seed=seed)


# ── planned: resident workers in their own venv ─────────────────────────────

class _WorkerModel:
    """Shared plumbing for a provider that runs as a resident ``SubprocessWorker``."""

    folder = ""
    script = "auralis_worker.py"

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else providers_root() / self.folder
        self.worker: SubprocessWorker | None = None

    @property
    def python(self) -> Path:
        return self.root / ".venv" / "Scripts" / "python.exe"

    def is_installed(self) -> bool:
        return self.python.is_file() and (self.root / self.script).is_file()

    def is_loaded(self) -> bool:
        return bool(self.worker and self.worker.running)

    def load(self) -> None:
        if not self.is_installed():
            raise ModelNotInstalledError(f"{self.spec.name} is not installed (see docs/MODEL_OPTIONS.md).")
        self.worker = SubprocessWorker(self.python, self.root / self.script, cwd=self.root)
        self.worker.start()

    def unload(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker = None


class ACEStepSections(_WorkerModel, SectionGenerator):
    folder = "ace-step"
    spec = ModelSpec(
        id="ace-step", kind="section_generator", name="ACE-Step (generated sections)",
        licence="Apache-2.0 (code and weights)", heavy=True, resident=True, vram_gb=10.0, commit_gb=16.0,
        min_commit_gb=12.0,
        notes="Not installed. Would render chosen blueprint sections as audio. Needs roughly 8-12 GB VRAM, so it "
              "must never be loaded together with Seed-VC: the model manager unloads one before loading the other.")

    def generate(self, request: SectionRequest) -> SectionResult:
        if not self.is_loaded():
            raise ModelNotInstalledError("ACE-Step is not loaded (use it through the model manager).")
        reply = self.worker.request(
            "generate_section", prompt=request.prompt, seconds=request.seconds, tempo=request.tempo,
            key=request.key, seed=request.seed, out_dir=request.out_dir, stems=list(request.stems))
        return SectionResult(paths=reply["paths"], sample_rate=int(reply.get("sample_rate", 44100)),
                             seconds=float(reply.get("seconds", request.seconds)), provider=self.spec.id,
                             notes=reply.get("notes", []))


class DiffSingerGuide(_WorkerModel, GuideSinger):
    folder = "diffsinger"
    spec = ModelSpec(
        id="diffsinger", kind="guide_singer", name="DiffSinger (lyric guide singer)",
        licence="Apache-2.0 engine; the voicebank has its own licence (English voicebanks found are "
                "non-commercial unless licensed)",
        heavy=True, resident=True, vram_gb=4.0, commit_gb=6.0, min_commit_gb=4.0,
        notes="Not installed. Would sing the guide score with real words; Seed-VC then turns it into the user's voice.")
    sings_words = True
    languages = ("en",)

    def sing(self, score, total_seconds, seed=0):
        import tempfile

        import soundfile as sf

        if not self.is_loaded():
            raise ModelNotInstalledError("DiffSinger is not loaded (use it through the model manager).")
        out = os.path.join(tempfile.mkdtemp(prefix="auralis_ds_"), "guide.wav")
        reply = self.worker.request("sing", notes=[n.to_dict() for n in score], seconds=total_seconds,
                                    seed=seed, out_path=out)
        audio, sr = sf.read(reply.get("path", out), dtype="float32")
        audio = audio.mean(axis=1) if audio.ndim == 2 else audio
        if sr != 44100:
            from scipy.signal import resample_poly
            audio = resample_poly(audio, 44100, sr).astype(np.float32)
        n = int(total_seconds * 44100) + 44100
        return np.pad(audio, (0, max(0, n - len(audio))))[:n].astype(np.float32)
