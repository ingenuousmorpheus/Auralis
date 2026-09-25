"""Engines behind interfaces, and their lifecycle (one heavy model on the GPU at a time).

``MODELS`` is the process-wide model manager and ``REGISTRY`` picks the engine
for each job kind. See ``lifecycle.py``, ``interfaces.py`` and ``builtin.py``.
"""
from .interfaces import (ConversionRequest, GuideSinger, SectionGenerator, SectionRequest, SectionResult,
                         VoiceConverter, section_prompt)
from .lifecycle import (POLICIES, ManagedModel, ModelManager, ModelMemoryError, ModelNotInstalledError, ModelSpec,
                        free_commit_gb)
from .registry import KINDS, Registry
from .worker import SubprocessWorker, WorkerError

MODELS = ModelManager()
REGISTRY = Registry(MODELS)

__all__ = ["KINDS", "MODELS", "POLICIES", "REGISTRY", "ConversionRequest", "GuideSinger", "ManagedModel",
           "ModelManager", "ModelMemoryError", "ModelNotInstalledError", "ModelSpec", "Registry", "SectionGenerator",
           "SectionRequest", "SectionResult", "SubprocessWorker", "VoiceConverter", "WorkerError", "free_commit_gb",
           "section_prompt"]
