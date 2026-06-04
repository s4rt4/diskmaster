"""Client for the privileged helper.

Spawns `core/privhelper.py` as root ONCE per session (via pkexec, or directly if
already root, or sudo as a last resort) and talks to it over a JSON-lines pipe.
Thread-safe: requests are serialised with a lock so multiple poller threads can
share one authenticated helper.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

_HELPER = Path(__file__).resolve().parent / "privhelper.py"


class PrivError(Exception):
    pass


class PrivClient:
    def __init__(self, timeout: float = 130.0):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._timeout = timeout
        self._method = self._detect_method()

    @staticmethod
    def _detect_method() -> str:
        """Determine the escalation method WITHOUT spawning (no auth prompt)."""
        if os.geteuid() == 0:
            return "root"
        if shutil.which("pkexec"):
            return "pkexec"
        if shutil.which("sudo"):
            return "sudo"
        return "none"

    # ------------------------------------------------------------- lifecycle --

    def _build_argv(self) -> list[str]:
        py = sys.executable or "python3"
        target = [py, str(_HELPER)]
        if os.geteuid() == 0:
            self._method = "root"
            return target
        if shutil.which("pkexec"):
            self._method = "pkexec"
            return ["pkexec", py, str(_HELPER)]
        if shutil.which("sudo"):
            self._method = "sudo"
            return ["sudo", py, str(_HELPER)]
        raise PrivError("no privilege escalation method available (pkexec/sudo)")

    @property
    def method(self) -> str:
        return self._method

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        """Spawn the helper and confirm it with a ping. Idempotent."""
        with self._lock:
            if self.is_alive():
                return
            argv = self._build_argv()
            try:
                self._proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # line-buffered
                )
            except OSError as e:
                raise PrivError(f"failed to spawn helper: {e}") from e
            # Confirm authentication / startup.
            resp = self._request_locked({"cmd": "ping"})
            if not resp.get("ok"):
                self._kill_locked()
                raise PrivError(f"helper ping failed: {resp.get('error')}")
            if not resp.get("data", {}).get("root"):
                self._kill_locked()
                raise PrivError("helper is not running as root")

    def _kill_locked(self) -> None:
        if self._proc:
            try:
                self._proc.kill()
            except OSError:
                pass
            self._proc = None

    def close(self) -> None:
        with self._lock:
            if self._proc and self._proc.stdin:
                try:
                    self._proc.stdin.close()
                except OSError:
                    pass
            if self._proc:
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._kill_locked()
            self._proc = None

    # -------------------------------------------------------------- requests --

    def _request_locked(self, req: dict) -> dict:
        proc = self._proc
        if not proc or proc.poll() is not None or not proc.stdin or not proc.stdout:
            return {"ok": False, "error": "helper not running"}
        try:
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            return {"ok": False, "error": f"write failed: {e}"}
        line = proc.stdout.readline()
        if not line:
            err = ""
            if proc.stderr:
                err = proc.stderr.read() or ""
            return {"ok": False, "error": f"helper closed pipe. {err.strip()}"}
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"bad response: {line[:200]!r}"}

    def request(self, cmd: str, **kwargs) -> dict:
        """Send a command, returning the helper's data or raising PrivError.

        Auto-respawns the helper once if it has died (will re-prompt for auth).
        """
        req = {"cmd": cmd, **kwargs}
        with self._lock:
            if not self.is_alive():
                # Respawn (best-effort) — this re-triggers pkexec auth.
                self._proc = None
            if not self._proc:
                # release lock to call start() which re-acquires it
                pass
        if not self.is_alive():
            self.start()
        with self._lock:
            resp = self._request_locked(req)
        if not resp.get("ok"):
            raise PrivError(resp.get("error", "unknown helper error"))
        return resp.get("data")

    # ------------------------------------------------------- typed shortcuts --

    def hdsentinel_xml(self) -> str:
        return self.request("hdsentinel_xml")

    def hdsentinel_solid(self) -> str:
        return self.request("hdsentinel_solid")

    def smart(self, device: str) -> dict:
        return self.request("smart", device=device)

    def nvme_smart(self, device: str) -> dict:
        return self.request("nvme_smart", device=device)

    def selftest_start(self, device: str, ttype: str) -> dict:
        return self.request("selftest_start", device=device, type=ttype)

    def selftest_log(self, device: str) -> dict:
        return self.request("selftest_log", device=device)

    def set_aam(self, drive: str, level: str) -> dict:
        return self.request("set_aam", drive=drive, level=level)

    def save_report(self, name: str, fmt: str = "txt") -> dict:
        return self.request("save_report", name=name, format=fmt)
