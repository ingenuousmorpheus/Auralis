"""Adapter for the separately installed GPL Seed-VC singing engine."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from ..engine.loudness import apply_true_peak_ceiling


def _provider_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Auralis" / "providers" / "seed-vc"


@dataclass
class ProviderStatus:
    installed: bool
    provider_dir: str
    python_path: str
    gpu_recommended: bool = True
    license: str = "GPL-3.0 (separate optional provider)"


class SeedVCProvider:
    def __init__(self, provider_dir: str | Path | None = None):
        self.root = Path(provider_dir) if provider_dir else _provider_root()
        self.python = self.root / ".venv" / "Scripts" / "python.exe"
        self.inference = self.root / "inference.py"

    def status(self) -> ProviderStatus:
        installed = self.python.exists() and self.inference.exists()
        return ProviderStatus(
            installed=installed,
            provider_dir=str(self.root),
            python_path=str(self.python),
        )

    def convert(
        self,
        source_path: str,
        reference_path: str,
        output_path: str,
        semitone_shift: int = 0,
        quality: str = "studio",
        checkpoint_path: str | None = None,
        config_path: str | None = None,
        progress=None,
    ) -> dict:
        if not self.status().installed:
            raise RuntimeError(
                "The local Seed-VC engine is not installed. Use Install Voice Engine first."
            )
        diffusion_steps = {"fast": 12, "studio": 35, "ultra": 50}.get(quality, 35)
        output_dir = Path(output_path).parent / "seed_vc_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("loading voice model", 15)

        command = [
            str(self.python),
            str(self.inference),
            "--source", str(Path(source_path).resolve()),
            "--target", str(Path(reference_path).resolve()),
            "--output", str(output_dir.resolve()),
            "--diffusion-steps", str(diffusion_steps),
            "--length-adjust", "1.0",
            "--inference-cfg-rate", "0.7",
            "--f0-condition", "True",
            "--auto-f0-adjust", "False",
            "--semi-tone-shift", str(int(semitone_shift)),
            "--fp16", "True",
        ]
        if checkpoint_path and config_path:
            command.extend([
                "--checkpoint", str(Path(checkpoint_path).resolve()),
                "--config", str(Path(config_path).resolve()),
            ])
        if progress:
            progress("converting vocal timbre", 35)
        completed = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60 * 30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "Unknown Seed-VC error")[-3000:]
            raise RuntimeError(f"Voice conversion failed: {tail}")

        candidates = sorted(output_dir.glob("vc_*.wav"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError("Voice conversion completed without producing a WAV file.")
        rendered, sr = sf.read(candidates[-1], always_2d=True, dtype="float32")
        rendered = apply_true_peak_ceiling(rendered, sr, -1.0)
        sf.write(output_path, rendered, sr, subtype="PCM_24")
        shutil.rmtree(output_dir, ignore_errors=True)
        if progress:
            progress("finalizing vocal", 95)
        return {
            "output_path": output_path,
            "provider": "seed-vc",
            "quality": quality,
            "diffusion_steps": diffusion_steps,
            "semitone_shift": semitone_shift,
            "sample_rate": sr,
            "model_mode": "studio-trained" if checkpoint_path else "instant",
        }

    def train(
        self,
        dataset_dir: str,
        profile_dir: str,
        profile_id: str,
        max_steps: int = 1000,
        progress=None,
    ) -> dict:
        """Fine-tune the official 44.1 kHz singing model, resuming when possible."""
        if not self.status().installed:
            raise RuntimeError("The local Seed-VC engine is not installed.")
        config = self.root / "configs" / "presets" / (
            "config_dit_mel_seed_uvit_whisper_base_f0_44k.yml"
        )
        train_script = self.root / "train.py"
        if not config.exists() or not train_script.exists():
            raise RuntimeError("Seed-VC training files are missing.")
        run_name = f"auralis_{profile_id}"
        save_every = max(100, min(500, max_steps // 2))
        command = [
            str(self.python),
            str(train_script),
            "--config", str(config),
            "--dataset-dir", str(Path(dataset_dir).resolve()),
            "--run-name", run_name,
            "--batch-size", "1",
            "--max-steps", str(max_steps),
            "--max-epochs", "1000",
            "--save-every", str(save_every),
            "--num-workers", "0",
            "--gpu", "0",
        ]
        if progress:
            progress("loading training model", 5, 0, None)
        process = subprocess.Popen(
            command,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        recent = []
        last_step = 0
        loss = None
        assert process.stdout is not None
        for line in process.stdout:
            clean = line.strip()
            if clean:
                recent.append(clean)
                recent = recent[-80:]
            match = re.search(r"step\s+(\d+),\s+loss:\s+([0-9.eE+-]+)", clean)
            if match:
                last_step = int(match.group(1))
                loss = float(match.group(2))
                pct = 8 + min(last_step / max(max_steps, 1), 1.0) * 87
                if progress:
                    progress("training studio voice", pct, last_step, loss)
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError("Studio Voice training failed:\n" + "\n".join(recent[-30:]))

        run_dir = self.root / "runs" / run_name
        trained_model = run_dir / "ft_model.pth"
        if not trained_model.exists():
            raise RuntimeError("Training ended without producing ft_model.pth.")
        destination = Path(profile_dir) / "model"
        destination.mkdir(parents=True, exist_ok=True)
        checkpoint_out = destination / "ft_model.pth"
        config_out = destination / config.name
        shutil.copy2(trained_model, checkpoint_out)
        shutil.copy2(config, config_out)
        if progress:
            progress("finalizing studio voice", 98, max_steps, loss)
        return {
            "checkpoint_path": str(checkpoint_out),
            "config_path": str(config_out),
            "training_steps": max_steps,
            "last_reported_step": last_step,
            "final_loss": loss,
            "run_name": run_name,
        }
