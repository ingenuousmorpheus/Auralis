"""A heavy model living in its own process: load = start it, unload = stop it.

Large engines (a generative section model like ACE-Step, a lyric singer like
DiffSinger) belong in their own virtual environment under
``%LOCALAPPDATA%/Auralis/providers/<name>/``, like Seed-VC, so their
dependencies and licences stay out of the MIT package.

``SubprocessWorker`` is the contract between Auralis and such a provider:

* **start** (``load``): run ``<python> <script>`` in the provider folder. The
  worker loads its weights, then prints one JSON line ``{"ready": true, ...}``.
* **request**: Auralis writes one JSON line ``{"id": n, "op": "...", ...}`` to
  stdin; the worker answers with one JSON line ``{"id": n, "ok": true, ...}`` or
  ``{"id": n, "ok": false, "error": "..."}``. Audio goes through files named in
  the request (never through the pipe).
* **stop** (``unload``): Auralis sends ``{"op": "shutdown"}``; if the worker
  hasn't exited within the grace period it is terminated. Its memory (RAM and
  VRAM) is released with the process.

The same worker can serve many requests while loaded, which is why keeping a
model warm (``ModelManager`` policy ``keep_warm``) can save load time.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path


class WorkerError(RuntimeError):
    pass


class SubprocessWorker:
    def __init__(self, python: str | Path, script: str | Path, cwd: str | Path | None = None,
                 ready_timeout: float = 600.0, request_timeout: float = 3600.0, env: dict | None = None):
        self.python, self.script = str(python), str(script)
        self.cwd = str(cwd) if cwd else str(Path(script).parent)
        self.ready_timeout, self.request_timeout = ready_timeout, request_timeout
        self.env = env
        self._proc: subprocess.Popen | None = None
        self._log = None
        self.log_path: str | None = None
        self._ids = 0
        self._lock = threading.Lock()
        self.info: dict = {}

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> dict:
        if self.running:
            return self.info
        import tempfile

        env = dict(os.environ, PYTHONIOENCODING="utf-8", **(self.env or {}))
        # stderr goes to a log file: an unread pipe would fill up and stall a chatty model
        fd, self.log_path = tempfile.mkstemp(prefix="auralis_worker_", suffix=".log")
        self._log = os.fdopen(fd, "w", encoding="utf-8")
        self._proc = subprocess.Popen(
            [self.python, self.script], cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._log, text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = self._readline(self.ready_timeout)
        if not line or not line.get("ready"):
            err = self._stderr_tail()
            self.stop()
            raise WorkerError(f"The model worker did not start: {line or ''} {err}".strip())
        self.info = line
        return line

    def request(self, op: str, **payload) -> dict:
        with self._lock:
            if not self.running:
                raise WorkerError("The model worker is not running (load it first).")
            self._ids += 1
            msg = {"id": self._ids, "op": op, **payload}
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
            reply = self._readline(self.request_timeout)
            if reply is None:
                raise WorkerError(f"The model worker stopped while working. {self._stderr_tail()}")
            if not reply.get("ok"):
                raise WorkerError(reply.get("error") or "The model worker reported an error.")
            return reply

    def stop(self, grace: float = 10.0) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.stdin.write(json.dumps({"op": "shutdown"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=grace)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                proc.kill()
                proc.wait(timeout=grace)
        for pipe in (proc.stdin, proc.stdout, self._log):
            try:
                if pipe:
                    pipe.close()
            except OSError:
                pass
        self._log = None

    # ── helpers ─────────────────────────────────────────────────────────
    def _readline(self, timeout: float) -> dict | None:
        result: list = []

        def read():
            while True:
                raw = self._proc.stdout.readline() if self._proc else ""
                if not raw:
                    return
                raw = raw.strip()
                if raw.startswith("{"):
                    try:
                        result.append(json.loads(raw))
                        return
                    except json.JSONDecodeError:
                        continue                   # progress text from the model; skip it

        t = threading.Thread(target=read, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise WorkerError(f"The model worker did not answer within {timeout:.0f} s.")
        return result[0] if result else None

    def _stderr_tail(self) -> str:
        try:
            if self._log:
                self._log.flush()
            if self.log_path and os.path.isfile(self.log_path):
                with open(self.log_path, encoding="utf-8", errors="replace") as f:
                    return f.read()[-1500:]
        except OSError:
            pass
        return ""
