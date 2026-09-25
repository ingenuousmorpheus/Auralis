"""Model lifecycle: one heavy model on the GPU at a time (roadmap §16).

Every heavy engine (Seed-VC today; a generative section model or a lyric singer
later) runs inside ``MODELS.use(model_id)``:

    with MODELS.use("seed-vc", label="convert chorus"):
        ...run the job...

which

1. waits for the single GPU slot (jobs never overlap; re-entrant in one thread),
2. checks free commit memory against the model's needs and fails early with a
   plain explanation instead of a mid-job ``os error 1455``,
3. unloads any other *resident* model first,
4. loads this one if it isn't loaded,
5. runs the job, then releases according to the policy:

   * ``balanced``  (default) unload right after the job: the GPU/VRAM is never
                   left occupied between jobs
   * ``keep_warm`` stay loaded until another model needs the slot, or until
                   ``idle_seconds`` pass (a sweep runs on every ``use``/``status``)
   * ``low_memory`` like balanced, and demand the model's full memory estimate
                   (not just the observed minimum) before loading

A model that runs as a per-call subprocess (Seed-VC's ``inference.py``) is not
resident: it loads and frees itself inside each call, so it only needs the slot
and the memory check. Resident models (a worker process holding weights, see
``worker.SubprocessWorker``) implement ``load``/``unload`` for real.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field

POLICIES = ("balanced", "keep_warm", "low_memory")


@dataclass
class ModelSpec:
    id: str
    kind: str                       # voice_converter | guide_singer | section_generator | instrumental_renderer
    name: str
    licence: str
    heavy: bool = False             # needs the GPU slot and a memory check
    resident: bool = False          # holds memory between calls until unloaded
    vram_gb: float = 0.0            # typical GPU memory while running
    commit_gb: float = 0.0          # typical system commit memory while running
    min_commit_gb: float = 0.0      # below this free commit, loading is known to fail
    notes: str = ""

    def to_dict(self):
        return asdict(self)


class ManagedModel:
    """What the manager needs from a model. Providers subclass this (or duck-type it)."""

    spec: ModelSpec

    def is_installed(self) -> bool:
        return True

    def is_loaded(self) -> bool:
        return False

    def load(self) -> None:
        """Bring weights into memory (resident models). Per-call models do nothing."""

    def unload(self) -> None:
        """Free the memory the model holds (resident models). Per-call models do nothing."""


class ModelMemoryError(RuntimeError):
    pass


class ModelNotInstalledError(RuntimeError):
    pass


def free_commit_gb() -> float | None:
    """Free system commit memory in GB (Windows page-file backed), or None if unknown."""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return None
        return stat.ullAvailPageFile / 1024 ** 3
    except (AttributeError, OSError):
        try:
            import psutil

            vm = psutil.virtual_memory()
            return (vm.available + psutil.swap_memory().free) / 1024 ** 3
        except Exception:                    # noqa: BLE001 - memory is advisory
            return None


@dataclass
class _State:
    loaded: set = field(default_factory=set)
    holder: str | None = None
    holder_label: str = ""
    last_used: dict = field(default_factory=dict)


class ModelManager:
    def __init__(self, memory=free_commit_gb, policy: str = "balanced", idle_seconds: float = 600.0):
        self._models: dict[str, ManagedModel] = {}
        self._slot = threading.Condition(threading.RLock())
        self._owner: int | None = None        # thread id holding the slot
        self._depth = 0
        self._state = _State()
        self._memory = memory
        self.policy = policy
        self.idle_seconds = idle_seconds
        self.events: deque = deque(maxlen=200)

    # ── registration ────────────────────────────────────────────────────
    def register(self, model: ManagedModel) -> ManagedModel:
        self._models[model.spec.id] = model
        return model

    def get(self, model_id: str) -> ManagedModel:
        if model_id not in self._models:
            raise KeyError(f"Unknown model: {model_id}")
        return self._models[model_id]

    def models(self) -> list[ManagedModel]:
        return list(self._models.values())

    def set_policy(self, policy: str) -> None:
        if policy not in POLICIES:
            raise ValueError(f"Policy must be one of {', '.join(POLICIES)}.")
        self.policy = policy
        self._log("policy", policy)
        if policy != "keep_warm":
            with self._slot:
                if self._owner is None:
                    self._unload_all(reason=f"policy {policy}")

    # ── the slot ────────────────────────────────────────────────────────
    @contextmanager
    def use(self, model_id: str, label: str = ""):
        model = self.get(model_id)
        if not model.is_installed():
            raise ModelNotInstalledError(f"{model.spec.name} is not installed.")
        me = threading.get_ident()
        with self._slot:
            while self._owner not in (None, me):
                self._slot.wait()
            if self._depth and self._state.holder not in (None, model_id):
                raise RuntimeError(f"{model.spec.name} can't start inside a {self._state.holder} job: "
                                   "one heavy model at a time, run the stages one after another.")
            self._owner = me
            self._depth += 1
        try:
            if self._depth == 1:
                self._sweep_idle()
                if model.spec.heavy:
                    self._check_memory(model)
                for other in list(self._state.loaded):
                    if other != model_id:
                        self._unload(other, reason=f"making room for {model.spec.name}")
                if model.spec.resident and model_id not in self._state.loaded:
                    t = time.monotonic()
                    model.load()
                    self._state.loaded.add(model_id)
                    self._log("load", model_id, f"{time.monotonic() - t:.1f}s")
                self._state.holder, self._state.holder_label = model_id, label
                self._log("start", model_id, label)
            yield model
        finally:
            with self._slot:
                self._depth -= 1
                if self._depth == 0:
                    self._state.last_used[model_id] = time.monotonic()
                    self._log("finish", model_id, label)
                    if self.policy != "keep_warm" and model_id in self._state.loaded:
                        self._unload(model_id, reason=f"policy {self.policy}")
                    self._state.holder, self._state.holder_label = None, ""
                    self._owner = None
                    self._slot.notify_all()

    def release_all(self, reason: str = "released by request") -> list[str]:
        with self._slot:
            while self._owner is not None:
                self._slot.wait()
            released = sorted(self._state.loaded)
            self._unload_all(reason)
            return released

    # ── internals ───────────────────────────────────────────────────────
    def _check_memory(self, model: ManagedModel) -> None:
        if os.environ.get("AURALIS_MEMORY_CHECK", "").lower() in ("off", "0", "false"):
            return
        free = self._memory() if self._memory else None
        if free is None:
            return
        need = model.spec.commit_gb if self.policy == "low_memory" else model.spec.min_commit_gb
        # memory already held by resident models we are about to unload counts as free
        reclaim = sum(self._models[m].spec.commit_gb for m in self._state.loaded if m != model.spec.id)
        if need and free + reclaim < need:
            self._log("refused", model.spec.id, f"{free:.1f} GB free, needs {need:.1f} GB")
            raise ModelMemoryError(
                f"{model.spec.name} needs about {need:.0f} GB of free memory but only {free:.1f} GB is free. "
                "Close large apps (for example a local LLM) or enlarge the page file, then try again.")

    def _unload(self, model_id: str, reason: str) -> None:
        if model_id in self._state.loaded:
            t = time.monotonic()
            self._models[model_id].unload()
            self._state.loaded.discard(model_id)
            self._log("unload", model_id, f"{reason} ({time.monotonic() - t:.1f}s)")

    def _unload_all(self, reason: str) -> None:
        for m in sorted(self._state.loaded):
            self._unload(m, reason)

    def _sweep_idle(self) -> None:
        if self.policy != "keep_warm":
            return
        now = time.monotonic()
        for m in list(self._state.loaded):
            if now - self._state.last_used.get(m, now) > self.idle_seconds:
                self._unload(m, reason=f"idle {self.idle_seconds:.0f}s")

    def _log(self, what: str, model_id: str, detail: str = "") -> None:
        self.events.append({"at": time.time(), "event": what, "model": model_id, "detail": detail})

    # ── status for the UI ───────────────────────────────────────────────
    def status(self) -> dict:
        with self._slot:
            if self._owner is None:
                self._sweep_idle()
            free = self._memory() if self._memory else None
            return {
                "policy": self.policy, "policies": list(POLICIES), "idle_seconds": self.idle_seconds,
                "busy": self._state.holder, "busy_with": self._state.holder_label,
                "loaded": sorted(self._state.loaded),
                "free_commit_gb": None if free is None else round(free, 1),
                "models": [dict(m.spec.to_dict(), installed=m.is_installed(), loaded=m.spec.id in self._state.loaded)
                           for m in self._models.values()],
                "events": list(self.events)[-20:],
            }
