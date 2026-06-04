#!/usr/bin/env python3
"""Privileged helper — runs as root, spawned ONCE per session by privclient.

Protocol: JSON-lines over stdin/stdout. One request object per line, one
response object per line:

    request : {"cmd": "<name>", ...args}
    response: {"ok": true, "data": ...}  |  {"ok": false, "error": "..."}

SECURITY MODEL
- Only the whitelisted commands in DISPATCH can run; no arbitrary execution.
- Device arguments are validated against the set of real physical block devices.
- Report paths are restricted to a safe directory.
- Binaries are resolved by the helper itself (not taken from the client) to keep
  the root-side trust boundary intact.

Run standalone for debugging:  sudo python3 core/privhelper.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Make `core` importable when launched as a bare script under pkexec.
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from core import paths  # noqa: E402

_TIMEOUT = 120  # seconds per external command
_REPORT_DIR = Path("/tmp/diskmaster")  # only place reports may be written


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}


def _ok(data) -> dict:
    return {"ok": True, "data": data}


def _allowed_devices() -> set[str]:
    return {f"/dev/{n}" for n in paths.physical_block_devices()}


def _check_device(device: str) -> str | None:
    """Return None if valid, else an error string."""
    if not device:
        return "missing device"
    if device not in _allowed_devices():
        return f"device not allowed: {device!r}"
    return None


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    # HDSentinel emits the degree sign (0xB0) and other Latin-1 bytes that are
    # not valid UTF-8, so decode leniently instead of letting text=True raise a
    # UnicodeDecodeError. We only ever parse numbers/XML out of this, so a
    # replacement char for the odd byte is harmless.
    return subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=_TIMEOUT, check=False
    )


# ---------------------------------------------------------------- commands ----

def cmd_ping(_req: dict) -> dict:
    return _ok({"pong": True, "uid": os.getuid(), "root": os.getuid() == 0})


def cmd_hdsentinel_xml(_req: dict) -> dict:
    binpath = paths.find_hdsentinel(str(_PKG_ROOT))
    if not binpath:
        return _err("hdsentinel binary not found")
    cp = _run([binpath, "-xml", "-dump"])
    if not cp.stdout.strip():
        return _err("hdsentinel produced no output (no disks or access denied)")
    return _ok(cp.stdout)


def cmd_hdsentinel_solid(_req: dict) -> dict:
    binpath = paths.find_hdsentinel(str(_PKG_ROOT))
    if not binpath:
        return _err("hdsentinel binary not found")
    # `-solid` (not `-solidi`): sizeMB is the last column, so the trailing
    # field is a single numeric token — robust to right-anchored parsing.
    # `-solidi` appends the interface, which can contain spaces.
    cp = _run([binpath, "-solid"])
    return _ok(cp.stdout)


def cmd_smart(req: dict) -> dict:
    device = req.get("device", "")
    if (e := _check_device(device)):
        return _err(e)
    sm = paths.find_smartctl()
    if not sm:
        return _err("smartctl not found")
    # nowake: ask smartctl to bail (CHECK POWER MODE only) if the drive is asleep
    # so a background poll never spins an idle disk up.
    argv = [sm]
    if req.get("nowake"):
        argv += ["-n", "standby"]
    argv += ["-a", "-j", device]
    cp = _run(argv)
    # smartctl uses bitfield exit codes; stdout JSON is still valid on warnings.
    try:
        return _ok(json.loads(cp.stdout))
    except json.JSONDecodeError:
        return _err(f"smartctl returned non-JSON (exit {cp.returncode})")


def cmd_power_mode(req: dict) -> dict:
    """Report the drive's ATA power mode without spinning it up."""
    device = req.get("device", "")
    if (e := _check_device(device)):
        return _err(e)
    sm = paths.find_smartctl()
    if not sm:
        return _err("smartctl not found")
    # `-n standby -i`: issues CHECK POWER MODE; only reads identity if awake.
    cp = _run([sm, "-n", "standby", "-i", "-j", device])
    try:
        return _ok(json.loads(cp.stdout))
    except json.JSONDecodeError:
        return _err(f"smartctl returned non-JSON (exit {cp.returncode})")


def cmd_selftest_start(req: dict) -> dict:
    device = req.get("device", "")
    if (e := _check_device(device)):
        return _err(e)
    ttype = req.get("type", "short")
    mapping = {"short": "short", "extended": "long", "long": "long",
               "conveyance": "conveyance"}
    if ttype not in mapping:
        return _err(f"unknown self-test type: {ttype!r}")
    sm = paths.find_smartctl()
    if not sm:
        return _err("smartctl not found")
    cp = _run([sm, "-t", mapping[ttype], device])
    return _ok({"returncode": cp.returncode, "output": cp.stdout})


def cmd_selftest_log(req: dict) -> dict:
    device = req.get("device", "")
    if (e := _check_device(device)):
        return _err(e)
    sm = paths.find_smartctl()
    if not sm:
        return _err("smartctl not found")
    # `-c` adds ata_smart_data.self_test.status (live progress / remaining %);
    # `-l selftest` adds the historical results table. Both in one JSON.
    cp = _run([sm, "-c", "-l", "selftest", "-j", device])
    try:
        return _ok(json.loads(cp.stdout))
    except json.JSONDecodeError:
        return _err("smartctl selftest log not JSON")


def cmd_nvme_smart(req: dict) -> dict:
    device = req.get("device", "")
    if (e := _check_device(device)):
        return _err(e)
    nv = paths.find_nvme()
    if not nv:
        return _err("nvme binary not found (install nvme-cli)")
    cp = _run([nv, "smart-log", device, "-o", "json"])
    try:
        return _ok(json.loads(cp.stdout))
    except json.JSONDecodeError:
        return _err(f"nvme returned non-JSON (exit {cp.returncode})")


def cmd_set_aam(req: dict) -> dict:
    drive = str(req.get("drive", ""))
    level = str(req.get("level", ""))
    if not drive or not level:
        return _err("set_aam requires 'drive' and 'level'")
    if level.upper() not in ("QUIET", "LOUD") and not _is_hex(level):
        return _err("level must be QUIET, LOUD, or hex 80-FE")
    binpath = paths.find_hdsentinel(str(_PKG_ROOT))
    if not binpath:
        return _err("hdsentinel binary not found")
    cp = _run([binpath, "-dev", drive, "-setaam", drive, level])
    return _ok({"returncode": cp.returncode, "output": cp.stdout})


def cmd_save_report(req: dict) -> dict:
    fmt = req.get("format", "txt").lower()
    if fmt not in ("txt", "html", "xml"):
        return _err("format must be txt/html/xml")
    name = os.path.basename(req.get("name", f"report.{fmt}"))
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = _REPORT_DIR / name
    binpath = paths.find_hdsentinel(str(_PKG_ROOT))
    if not binpath:
        return _err("hdsentinel binary not found")
    argv = [binpath, "-r", str(target)]
    if fmt == "xml":
        argv.append("-xml")
    elif fmt == "html":
        argv.append("-html")
    _run(argv)
    if not target.exists():
        return _err("report was not produced")
    return _ok({"path": str(target)})


def _is_hex(s: str) -> bool:
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


DISPATCH = {
    "ping": cmd_ping,
    "hdsentinel_xml": cmd_hdsentinel_xml,
    "hdsentinel_solid": cmd_hdsentinel_solid,
    "smart": cmd_smart,
    "power_mode": cmd_power_mode,
    "nvme_smart": cmd_nvme_smart,
    "selftest_start": cmd_selftest_start,
    "selftest_log": cmd_selftest_log,
    "set_aam": cmd_set_aam,
    "save_report": cmd_save_report,
}


def _handle(line: str) -> dict:
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        return _err("invalid JSON request")
    cmd = req.get("cmd")
    handler = DISPATCH.get(cmd)
    if not handler:
        return _err(f"unknown command: {cmd!r}")
    try:
        return handler(req)
    except subprocess.TimeoutExpired:
        return _err(f"command '{cmd}' timed out")
    except Exception as e:  # noqa: BLE001 — helper must never crash on one cmd
        return _err(f"{type(e).__name__}: {e}")


def main() -> int:
    # Unbuffered line protocol.
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        resp = _handle(raw)
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
