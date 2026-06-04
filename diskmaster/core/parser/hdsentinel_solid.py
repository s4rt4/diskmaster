"""Parse `hdsentinel -solid` / `-solidi` output for cheap, frequent updates.

The binary's own help documents the column order:

    -solid  : drv, tempC, health%, pow.onHours, model, S/N, sizeMB
    -solidi : drv, tempC, health%, pow.onHours, model, S/N, sizeMB, interface

Columns are whitespace-separated, but the *model* field contains spaces
(e.g. "TOSHIBA MQ01ABD032"), so a naive split is ambiguous. We anchor from both
ends instead: the device + three numerics are fixed on the left, and sizeMB
(+ optional interface for -solidi) + serial are fixed on the right; whatever
remains in the middle is the model.

NOTE: column order is confirmed from `hdsentinel -h`, but the exact whitespace
and a real multi-disk sample still want a cross-check on a root-capable machine.
The full XML scan remains the source of truth; this only patches temp/health/POH
between full scans, so a mis-parse self-corrects on the next full poll.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SolidRow:
    device: str
    temp_current: int
    health: int
    power_on_hours: int
    model: str
    serial: str
    size_gb: float


def _to_int(tok: str) -> int:
    m = re.search(r"-?\d+", tok or "")
    return int(m.group()) if m else -1


def _is_intish(tok: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", tok or ""))


def parse_solid(text: str, with_interface: bool = False) -> list[SolidRow]:
    """Parse solid output into rows. Unparseable lines are skipped.

    ``with_interface`` matches ``-solidi`` (one extra trailing column).
    """
    rows: list[SolidRow] = []
    trailing = 1 + (1 if with_interface else 0)  # sizeMB [+ interface]
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        toks = line.split()
        # device + temp + health + poh + model(>=1) + serial + sizeMB[+iface]
        if len(toks) < 6 + trailing:
            continue
        device = toks[0]
        if "/dev/" not in device and not device.startswith("/dev"):
            # Header or summary line, not a disk row.
            continue
        if not (_is_intish(toks[1]) and _is_intish(toks[2]) and _is_intish(toks[3])):
            continue
        # Right anchor: sizeMB is the last numeric column (before interface).
        size_idx = len(toks) - trailing
        size_mb = _to_int(toks[size_idx])
        serial = toks[size_idx - 1]
        model = " ".join(toks[4:size_idx - 1]).strip()
        rows.append(
            SolidRow(
                device=device,
                temp_current=_to_int(toks[1]),
                health=_to_int(toks[2]),
                power_on_hours=_to_int(toks[3]),
                model=model,
                serial=serial,
                size_gb=round(size_mb / 1000, 2) if size_mb > 0 else 0.0,
            )
        )
    return rows


__all__ = ["parse_solid", "SolidRow"]
