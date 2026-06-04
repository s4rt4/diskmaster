"""Tests for Phase 2/3 core: db, sysfs sampler, nvme parser, notifier.

Qt-free so they run headless. Run: python -m pytest tests/ -q
(or directly: python tests/test_phase2.py)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "diskmaster"))

from core.db import HistoryDB  # noqa: E402
from core.models import DiskInfo, DiskType, Status, SmartAttribute  # noqa: E402
from core.backends import sysfs, nvme  # noqa: E402
from core.notifier import Notifier, TEMP_HIGH, HEALTH_LOW  # noqa: E402


class DummySettings:
    """Minimal stand-in for config.Settings."""
    def __init__(self, **thresholds):
        self._t = {"temp_hdd": 55, "temp_ssd": 70, "temp_nvme": 75,
                   "health_min": 80}
        self._t.update(thresholds)

    def get(self, section, key, default=None):
        if section == "thresholds":
            return self._t.get(key, default)
        return default


def test_db_record_and_query():
    db = HistoryDB(":memory:")
    disks = [
        DiskInfo(device="/dev/sda", serial="SN1", health=89, temp_current=34),
        DiskInfo(device="/dev/sdb", serial="", health=-1, temp_current=-1),  # skip
    ]
    n = db.record_disks(disks, ts=1000)
    assert n == 1, f"only the disk with data should be stored, got {n}"
    db.record_disks([disks[0]], ts=2000)

    hist = db.history("SN1")
    assert len(hist) == 2
    assert hist[0].temp == 34 and hist[0].health == 89
    assert "SN1" in db.identities()
    print("OK test_db_record_and_query")


def test_db_smart_alerts_cleanup():
    db = HistoryDB(":memory:")
    attrs = [SmartAttribute(5, "Reallocated", 100, 100, 10, 0)]
    assert db.record_smart("SN1", attrs, ts=1000) == 1

    db.add_alert("SN1", "TEMP_HIGH", "hot", ts=1000)
    assert len(db.recent_alerts()) == 1

    # old row dropped, alert kept
    db.record_disks([DiskInfo(device="/dev/sda", serial="SN1", temp_current=30)],
                    ts=1000)
    import time
    far_future_days = (time.time() - 1000) / 86400 + 1  # makes ts=1000 "old"
    deleted = db.cleanup(int(far_future_days) - 1)
    assert deleted >= 1
    assert len(db.recent_alerts()) == 1  # alerts survive cleanup
    print("OK test_db_smart_alerts_cleanup")


def test_sysfs_throughput_math(monkeypatch=None):
    fake = {
        "x": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    }
    orig = sysfs._read_stat
    sysfs._read_stat = lambda name: fake[name]
    try:
        s = sysfs.IOSampler()
        assert s.sample("x", now=0.0) is not None  # primes to zero
        # 1MB read, 2MB written, 500ms busy over 1 second
        fake["x"] = [0, 0, 2048, 0, 0, 0, 4096, 0, 0, 500]
        st = s.sample("x", now=1.0)
        assert abs(st.read_mbps - 1.049) < 0.01, st.read_mbps
        assert abs(st.write_mbps - 2.097) < 0.01, st.write_mbps
        assert abs(st.utilization_pct - 50.0) < 0.5, st.utilization_pct
    finally:
        sysfs._read_stat = orig
    print("OK test_sysfs_throughput_math")


def test_nvme_parse_and_enrich():
    sample = {
        "temperature": 313,          # 313 K ≈ 40 °C
        "percentage_used": 7,
        "power_on_hours": 1234,
        "available_spare": 100,
        "critical_warning": 0,
        "media_errors": 0,
    }
    s = nvme.parse_nvme_smart(sample)
    assert s["temp_c"] == 40, s["temp_c"]
    assert s["percentage_used"] == 7

    disk = DiskInfo(device="/dev/nvme0n1")
    nvme.enrich_disk(disk, sample)
    assert disk.disk_type == DiskType.NVME
    assert disk.temp_current == 40
    assert disk.health == 93  # 100 - 7
    assert disk.power_on_hours == 1234
    assert disk.status == Status.GOOD
    print("OK test_nvme_parse_and_enrich")


def test_notifier_rising_edge():
    settings = DummySettings(temp_hdd=50, health_min=80)
    n = Notifier(settings)
    hot = DiskInfo(device="/dev/sda", serial="SN1", disk_type=DiskType.HDD,
                   temp_current=60, health=90)

    alerts = n.check([hot])
    assert len(alerts) == 1 and alerts[0].alert_type == TEMP_HIGH

    # still hot -> no repeat
    assert n.check([hot]) == []

    # cools down -> re-arm, no alert
    cool = DiskInfo(device="/dev/sda", serial="SN1", disk_type=DiskType.HDD,
                    temp_current=40, health=70)  # but health now low
    alerts = n.check([cool])
    types = {a.alert_type for a in alerts}
    assert HEALTH_LOW in types and TEMP_HIGH not in types
    print("OK test_notifier_rising_edge")


if __name__ == "__main__":
    test_db_record_and_query()
    test_db_smart_alerts_cleanup()
    test_sysfs_throughput_math()
    test_nvme_parse_and_enrich()
    test_notifier_rising_edge()
    print("\nALL PASSED")
