"""Map a finished in-memory job onto the project assets it should become.

This is the bridge that lets every existing workflow (master, mix, voice
conversion, pitch polish, vocal finish, auto polish) save into a project
without changing how those workflows run.

Reference tracks are deliberately never imported. A reference is the user's
copy of someone else's song and, by the mastering design, lives only in the
job's temp folder.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Result settings worth keeping as provenance. Scalars only.
_PROVENANCE_KEYS = (
    "profile_id", "mode", "reference_used", "before_lufs", "after_lufs",
    "before_peak_db", "after_peak_db", "provider", "quality", "diffusion_steps",
    "semitone_shift", "model_mode", "profile_name", "style", "notes_detected",
    "notes_corrected", "seed", "tempo", "blueprint_id", "blueprint_revision",
)


@dataclass
class JobOutput:
    path: str
    kind: str
    role: str
    name: str
    metadata: dict = field(default_factory=dict)


def job_kind(job: dict) -> str:
    """The job's kind. Master and mix jobs predate the ``kind`` field."""
    if job.get("kind"):
        return job["kind"]
    result = job.get("result") or {}
    if "stem_analyses" in result:
        return "mix"
    if job.get("input") or "mode" in result:
        return "master"
    return "unknown"


def job_outputs(job: dict) -> list[JobOutput]:
    """Return the files a finished job should contribute to a project."""
    if job.get("stage") != "done" or not job.get("result"):
        raise ValueError("Only finished jobs can be saved to a project.")
    kind = job_kind(job)
    result = job["result"]
    provenance = {k: result[k] for k in _PROVENANCE_KEYS
                  if isinstance(result.get(k), (str, int, float, bool))}
    if isinstance(result.get("master_result"), dict):
        provenance.update({k: v for k, v in result["master_result"].items()
                           if k in _PROVENANCE_KEYS and isinstance(v, (str, int, float, bool))})
    if isinstance(result.get("key"), dict) and result["key"].get("name"):
        provenance["key"] = result["key"]["name"]

    outputs: list[JobOutput] = []

    def add(path, asset_kind, role, name=None):
        if path and os.path.isfile(path):
            outputs.append(JobOutput(
                path=path, kind=asset_kind, role=role,
                name=name or os.path.basename(path), metadata=dict(provenance),
            ))

    if kind == "master":
        add(job.get("input"), "source", "stereo mix", _named(job, "mix"))
        add(result.get("output_path"), "master", "master", "master.wav")
    elif kind == "mix":
        for stem in job.get("stems", []):
            add(stem.get("path"), "stem", "stem", stem.get("filename"))
        add(result.get("mix_path"), "mix", "pre-master mix", "pre_master.wav")
        add(result.get("master_path"), "master", "master", "master.wav")
        add(result.get("report_path"), "report", "mix report", "mix_report.md")
        add(result.get("session_path"), "report", "mix session", "mix_session.json")
    elif kind == "voice-conversion":
        add(job.get("input"), "source", "guide vocal", _named(job, "guide"))
        add(result.get("output_path"), "vocal", "converted vocal", "my_voice.wav")
    elif kind == "pitch-polish":
        add(result.get("output_path"), "vocal", "pitch-polished vocal", "pitch_polished.wav")
        add(result.get("report_path"), "report", "pitch polish report", "pitch_polish.json")
    elif kind == "vocal-finish":
        if not job.get("source_job_id"):
            # Rack mode: the vocal was uploaded directly, so it is a source.
            add(result.get("source_path"), "source", "rack input vocal")
        add(result.get("output_path"), "vocal", "finished vocal", "finished_vocal.wav")
        add(result.get("preview_path"), "mix", "vocal in instrumental", "vocal_preview.wav")
        add(result.get("report_path"), "report", "vocal finish report", "vocal_finish.json")
    elif kind == "auto-studio-polish":
        add(result.get("pitch_path"), "vocal", "pitch-polished vocal", "pitch_polished.wav")
        add(result.get("output_path"), "vocal", "studio-polished vocal", "studio_polished.wav")
        add(result.get("preview_path"), "mix", "vocal in instrumental", "studio_preview.wav")
    elif kind == "instrumental-render":
        for part, path in (result.get("stems") or {}).items():
            add(path, "stem", f"{part} stem", f"{part}.wav")
        add(result.get("mix_path"), "mix", "instrumental pre-master", "instrumental_pre_master.wav")
        add(result.get("master_path"), "master", "instrumental master", "instrumental.wav")
        add(result.get("melody_guide_path"), "generated", "melody guide (not in the instrumental)",
            "melody_guide.wav")
        add(result.get("midi_path"), "generated", "arrangement MIDI", "arrangement.mid")
        add(result.get("blueprint_path"), "generated", "blueprint used", "blueprint_rendered.json")
        add(result.get("report_path"), "report", "mix report", "mix_report.md")
    elif kind == "song-vocal":
        add(result.get("song_master_path"), "master", "song master", "song.wav")
        add(result.get("song_mix_path"), "mix", "song pre-master", "song_pre_master.wav")
        add(result.get("finished_path"), "vocal", "finished lead vocal", "lead_vocal.wav")
        add(result.get("polished_path"), "vocal", "pitch-polished lead vocal", "lead_vocal_pitch.wav")
        add(result.get("converted_path"), "vocal", "converted lead vocal", "lead_vocal_raw.wav")
        add(result.get("backing_path"), "vocal", "backing vocals (bus)", "backing_vocals.wav")
        for part, path in (result.get("backing_stems") or {}).items():
            add(path, "vocal", f"backing vocal: {part.replace('_', ' ')}", f"bv_{part}.wav")
        add(result.get("guide_path"), "generated", "guide vocal", "guide_vocal.wav")
        add(result.get("report_path"), "report", "song mix report", "song_mix_report.md")
    else:
        raise ValueError(f"Jobs of kind '{kind}' have nothing to save to a project.")

    if not outputs:
        raise ValueError("This job's files are no longer available.")
    return outputs


def _named(job: dict, fallback: str) -> str:
    """Prefer the user's original upload name for inputs."""
    name = job.get("filename")
    return name if name else fallback + os.path.splitext(job.get("input") or ".wav")[1]
