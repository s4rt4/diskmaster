"""Parse `hdsentinel -xml` output into DiskInfo records.

HDSentinel builds its XML element names dynamically and they vary slightly
between versions (e.g. ``Disk_Model_ID`` vs ``Hard_Disk_Model_ID``). Rather than
hard-coding exact tags, we match by *normalised* tag name (lowercased,
non-alphanumerics stripped) against candidate lists. This keeps the parser robust
across versions.

NOTE: candidate tag lists were derived from HDSentinel's text-report labels and
need a final cross-check against real `hdsentinel -xml` output on a root-capable
machine. The structure (container-per-disk) is stable; only tag spelling varies.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..models import DiskInfo, DiskType, Status


class HDSentinelParseError(Exception):
    pass


def _norm(tag: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tag.lower())


def _first_int(text: str) -> int:
    m = re.search(r"-?\d+", text or "")
    return int(m.group()) if m else -1


def _parse_size_gb(text: str) -> float:
    """'305245 MB' / '298 GB' / '1.82 TB' -> GB (decimal)."""
    if not text:
        return 0.0
    m = re.search(r"([\d.,]+)\s*(TB|GB|MB|KB)?", text.strip(), re.IGNORECASE)
    if not m:
        return 0.0
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "MB").upper()
    factor = {"KB": 1e-6, "MB": 1e-3, "GB": 1.0, "TB": 1e3}.get(unit, 1e-3)
    return round(num * factor, 2)


def _parse_duration_hours(text: str) -> int:
    """'133 days, 2 hours' / '44 hours' -> total hours. -1 if nothing found."""
    if not text:
        return -1
    days = re.search(r"(\d+)\s*day", text, re.IGNORECASE)
    hours = re.search(r"(\d+)\s*hour", text, re.IGNORECASE)
    if not days and not hours:
        n = _first_int(text)
        return n if n >= 0 else -1
    total = 0
    if days:
        total += int(days.group(1)) * 24
    if hours:
        total += int(hours.group(1))
    return total


# Candidate normalised tag names per field (order = priority).
_FIELDS = {
    "device": ["diskdevice", "harddiskdevice", "device", "physicaldevice"],
    "model": ["diskmodelid", "harddiskmodelid", "modelid", "model"],
    "serial": ["harddiskserialnumber", "diskserialnumber", "serialnumber", "serial"],
    "firmware": ["firmwarerevision", "firmware"],
    "size": ["totalsize", "disksize", "size"],
    "temp": ["currenttemperature", "temperature", "temp"],
    "temp_max": [
        "maximumtemperatureduringentirelifespan",
        "maximumtemperature",
        "lifetimemaximumtemperature",
        "maxtemperature",
    ],
    "health": ["health"],
    "performance": ["performance"],
    "power_on": ["powerontime", "poweronhours", "powerontimecount"],
    "lifetime": ["estimatedremaininglifetime", "remaininglifetime", "estimatedlifetime"],
    "status": ["healthtext", "description", "overallhealthrating", "tip"],
}


def _index_texts(container: ET.Element) -> dict[str, str]:
    """Map normalised tag -> text for every descendant (first wins)."""
    out: dict[str, str] = {}
    for el in container.iter():
        key = _norm(el.tag)
        if key not in out and el.text and el.text.strip():
            out[key] = el.text.strip()
    return out


def _pick(texts: dict[str, str], field: str) -> str:
    for cand in _FIELDS[field]:
        if cand in texts:
            return texts[cand]
    return ""


def _classify(model: str, interface: str, device: str) -> DiskType:
    blob = f"{model} {interface} {device}".lower()
    if "nvme" in blob:
        return DiskType.NVME
    if "ssd" in blob or "solid" in blob:
        return DiskType.SSD
    if "ata" in interface.lower() or "hdd" in blob:
        return DiskType.HDD
    return DiskType.UNKNOWN


def _find_disk_containers(root: ET.Element) -> list[ET.Element]:
    # Primary: elements whose tag marks a physical-disk block.
    containers = [
        el for el in root.iter()
        if _norm(el.tag).startswith("physicaldiskinformation")
    ]
    if containers:
        return containers
    # Fallback: any element directly holding a device-like child, excluding
    # the summary block.
    fallback = []
    for el in root.iter():
        if _norm(el.tag).startswith("harddisksummary"):
            continue
        child_tags = {_norm(c.tag) for c in el}
        if child_tags & set(_FIELDS["device"]) and child_tags & set(_FIELDS["model"]):
            fallback.append(el)
    return fallback


def parse_xml(xml_text: str) -> list[DiskInfo]:
    """Parse XML string -> list[DiskInfo]. Raises on empty/invalid input."""
    if not xml_text or not xml_text.strip():
        raise HDSentinelParseError(
            "HDSentinel returned empty output — likely missing root privileges "
            "or no disks detected."
        )
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise HDSentinelParseError(f"Invalid XML from HDSentinel: {e}") from e

    disks: list[DiskInfo] = []
    for container in _find_disk_containers(root):
        texts = _index_texts(container)
        device = _pick(texts, "device")
        if not device:
            continue
        model = _pick(texts, "model")
        interface = texts.get("interface", "")
        disk = DiskInfo(
            device=device,
            model=model,
            serial=_pick(texts, "serial"),
            firmware=_pick(texts, "firmware"),
            size_gb=_parse_size_gb(_pick(texts, "size")),
            disk_type=_classify(model, interface, device),
            health=_first_int(_pick(texts, "health")),
            performance=_first_int(_pick(texts, "performance")),
            temp_current=_first_int(_pick(texts, "temp")),
            temp_max=_first_int(_pick(texts, "temp_max")),
            power_on_hours=_parse_duration_hours(_pick(texts, "power_on")),
            estimated_lifetime=_pick(texts, "lifetime"),
            status=Status.from_text(_pick(texts, "status")),
        )
        disks.append(disk)

    if not disks:
        raise HDSentinelParseError(
            "No disks found in HDSentinel XML — output structure unrecognised."
        )
    return disks
