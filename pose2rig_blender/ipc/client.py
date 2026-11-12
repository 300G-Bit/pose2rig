"""Blender-side worker client.

The worker runs in a separate process.  A background thread only performs
process I/O; Blender scene changes happen in a timer callback on the main
thread (see ui/operators.py).
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


class WorkerError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, python_exe: str | None = None, server_script: str | None = None):
        self.python_exe = python_exe or sys.executable
        if server_script is None:
            server_script = str(Path(__file__).resolve().parent.parent / "worker" / "server.py")
        self.server_script = server_script
        self._lock = threading.Lock()
        self._process = None
        self._cancelled = False

    def cancel(self):
        with self._lock:
            self._cancelled = True
            proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def submit(self, request: dict, result_queue: queue.Queue, timeout_s: float = 180.0):
        thread = threading.Thread(target=self._run, args=(request, result_queue, timeout_s), daemon=True)
        thread.start()
        return thread

    def _run(self, request, result_queue, timeout_s):
        request_id = request.get("request_id") or str(uuid.uuid4())
        request["request_id"] = request_id
        env = os.environ.copy()
        package_root = str(Path(self.server_script).resolve().parents[2])
        env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
        proc = None
        stderr_lines = []
        try:
            proc = subprocess.Popen(
                [self.python_exe, self.server_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=package_root,
                env=env,
            )
            with self._lock:
                self._process = proc
            if self._cancelled:
                proc.terminate()
                result_queue.put({"type": "cancelled", "request_id": request_id})
                return

            lines = queue.Queue()

            def read_stdout():
                for line in proc.stdout:
                    lines.put(line)

            def read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line)
                    if len(stderr_lines) > 80:
                        del stderr_lines[:-80]

            threading.Thread(target=read_stdout, daemon=True).start()
            threading.Thread(target=read_stderr, daemon=True).start()

            proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            proc.stdin.flush()

            deadline = time.monotonic() + timeout_s
            response = None
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=0.5)
                except queue.Empty:
                    if proc.poll() is not None:
                        break
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("request_id") == request_id or msg.get("type") in ("result", "error"):
                    response = msg
                    break
            if response is None:
                if proc.poll() is None:
                    proc.terminate()
                raise WorkerError("worker returned no response. stderr:\n" + "".join(stderr_lines)[-4000:])
            result_queue.put(response)
        except Exception as exc:  # noqa: BLE001
            result_queue.put({
                "type": "error",
                "request_id": request_id,
                "error": {"code": "CLIENT_ERROR", "message": f"{type(exc).__name__}: {exc}", "details": []},
            })
        finally:
            if proc is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            with self._lock:
                self._process = None
