"""Config manager — TOML at ~/.config/diskmaster/config.toml.

Read via stdlib tomllib (3.11+). Write via a tiny serialiser for our flat schema
so we need no third-party TOML dependency.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

_XDG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
CONFIG_DIR = Path(_XDG) / "diskmaster"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULTS: dict = {
    "general": {
        "start_minimized": False,
        "theme": "system",          # system / dark / light
    },
    "polling": {
        "quick_interval_sec": 30,
        "full_interval_sec": 300,
        "skip_standby": True,
    },
    "thresholds": {
        "temp_hdd": 55,
        "temp_ssd": 70,
        "temp_nvme": 75,
        "health_min": 80,
    },
    "paths": {
        "hdsentinel": "",           # empty = auto-detect
        "smartctl": "",
    },
    "history": {
        "retention_days": 90,
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dump_toml(data: dict) -> str:
    lines: list[str] = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, val in values.items():
            lines.append(f"{key} = {_toml_value(val)}")
        lines.append("")
    return "\n".join(lines)


class Settings:
    def __init__(self):
        self._data = _merge(DEFAULTS, self._load())

    def _load(self) -> dict:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "rb") as f:
                    return tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                return {}
        return {}

    def get(self, section: str, key: str, default=None):
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value) -> None:
        self._data.setdefault(section, {})[key] = value

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(_dump_toml(self._data))

    @property
    def data(self) -> dict:
        return self._data
