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
from core.parser.hdsentinel_solid import parse_solid  # noqa: E402
from core.parser.hdsentinel_xml import _classify_status  # noqa: E402


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


_SOLID = """
HDSentinel header line that should be ignored
/dev/sda 34 89 3194 TOSHIBA MQ01ABD032 X5J7TABCS 305245
/dev/nvme0n1 38 95 1200 Samsung SSD 980 1TB S5GXNF0R 1000204

"""


def test_solid_parse_both_ends():
    rows = parse_solid(_SOLID, with_interface=False)
    assert len(rows) == 2, f"expected 2 rows, got {len(rows)}"

    sda = rows[0]
    assert sda.device == "/dev/sda"
    assert sda.temp_current == 34 and sda.health == 89
    assert sda.power_on_hours == 3194
    assert sda.model == "TOSHIBA MQ01ABD032"   # model with a space
    assert sda.serial == "X5J7TABCS"
    assert abs(sda.size_gb - 305.245) < 0.01

    nv = rows[1]
    assert nv.device == "/dev/nvme0n1"
    assert nv.model == "Samsung SSD 980 1TB"   # multi-word model
    assert nv.serial == "S5GXNF0R"
    assert nv.health == 95
    print("OK test_solid_parse_both_ends")


def test_status_classification():
    from core.models import Status
    # Real sda: communication-error note (contains "Problems"), Tip says fine,
    # health 100 → must NOT be downgraded to WARNING.
    sda = _classify_status(
        "Problems occurred between the communication of the disk and the host "
        "607 times. ... try different cables to prevent further problems.",
        "No actions needed.", 100)
    assert sda == Status.PERFECT, sda

    # Real sdb: explicit "status ... is PERFECT" wins over 66% health + monitor.
    sdb = _classify_status(
        "The status of the solid state disk is PERFECT. Problematic or weak "
        "sectors were not found.",
        "It is recommended to continuously monitor the hard disk status.", 66)
    assert sdb == Status.PERFECT, sdb

    # No explicit word + low health + backup advice → WARNING.
    assert _classify_status("Some weak sectors detected.",
                            "Back up important data.", 62) == Status.WARNING
    # Replacement advice → FAILURE regardless of wording.
    assert _classify_status("", "Replace the disk immediately.", 40) == Status.FAILURE
    # Explicit FAILURE word.
    assert _classify_status("The hard disk status is FAILURE.", "", 10) == Status.FAILURE
    print("OK test_status_classification")


def test_selftest_persist():
    db = HistoryDB(":memory:")
    # Start a test → one running row, returns id.
    tid = db.selftest_start("SER123", "/dev/sda", "extended")
    assert isinstance(tid, int) and tid > 0
    run = db.selftest_running("SER123")
    assert run and run["status"] == "running" and run["test_type"] == "extended"

    # Starting another supersedes the first (aborted), one running remains.
    db.selftest_start("SER123", "/dev/sda", "short")
    run = db.selftest_running("SER123")
    assert run["test_type"] == "short"
    aborted = [r for r in db.selftest_recent("SER123") if r["status"] == "aborted"]
    assert len(aborted) == 1

    # Finishing closes the running row; none left running.
    assert db.selftest_finish("SER123", "completed",
                              "Completed without error") is True
    assert db.selftest_running("SER123") is None
    assert db.selftest_finish("SER123") is False  # nothing open now

    # A different disk is isolated.
    assert db.selftest_running("OTHER") is None
    db.close()
    print("OK test_selftest_persist")


def test_power_mode_parse():
    from core.backends.smartctl import power_mode_from_json, is_asleep
    # smartctl -n standby on a sleeping drive: skip message + exit bit 1 set.
    standby = {"smartctl": {"exit_status": 2, "messages": [
        {"string": "Device is in STANDBY mode, exit(2)",
         "severity": "information"}]}}
    assert power_mode_from_json(standby) == "standby"
    assert is_asleep(standby) is True

    sleep = {"smartctl": {"exit_status": 2, "messages": [
        {"string": "Device is in SLEEP mode, exit(2)"}]}}
    assert power_mode_from_json(sleep) == "sleep"
    assert is_asleep(sleep) is True

    # Awake drive: smartctl proceeded, clean exit, full payload present.
    awake = {"smartctl": {"exit_status": 0, "messages": []},
             "ata_smart_attributes": {"table": []}}
    assert power_mode_from_json(awake) == "active"
    assert is_asleep(awake) is False

    # Idle/active are reported as awake (not asleep) and never suppress a read.
    idle = {"smartctl": {"exit_status": 0, "messages": [
        {"string": "Device is in IDLE mode"}]}}
    assert power_mode_from_json(idle) == "idle"
    assert is_asleep(idle) is False

    # Garbage in → unknown, and unknown must not be treated as asleep.
    assert power_mode_from_json({}) == "unknown"
    assert is_asleep({}) is False
    print("OK test_power_mode_parse")


if __name__ == "__main__":
    test_db_record_and_query()
    test_db_smart_alerts_cleanup()
    test_sysfs_throughput_math()
    test_nvme_parse_and_enrich()
    test_notifier_rising_edge()
    test_solid_parse_both_ends()
    test_status_classification()
    test_selftest_persist()
    test_power_mode_parse()
    print("\nALL PASSED")
