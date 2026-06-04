"""Smoke tests for the non-privileged core: parser + paths.

Run: python -m pytest tests/ -q   (or just: python tests/test_core.py)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "diskmaster"))

from core.parser.hdsentinel_xml import parse_xml, HDSentinelParseError  # noqa: E402
from core.models import DiskType, Status  # noqa: E402
from core import paths  # noqa: E402


SAMPLE_XML = """<?xml version="1.0"?>
<Hard_Disk_Sentinel>
  <Hard_Disk_Summary>
    <Number_of_Hard_Disks>2</Number_of_Hard_Disks>
  </Hard_Disk_Summary>
  <Physical_Disk_Information_Disk_HDD_0>
    <Disk_Device>/dev/sda</Disk_Device>
    <Interface>S-ATA Gen2, 3 Gbps</Interface>
    <Disk_Model_ID>TOSHIBA MQ01ABD032</Disk_Model_ID>
    <Firmware_Revision>AX001U</Firmware_Revision>
    <Hard_Disk_Serial_Number>X5J7TABCS</Hard_Disk_Serial_Number>
    <Total_Size>305245 MB</Total_Size>
    <Power_on_Time>133 days, 2 hours</Power_on_Time>
    <Current_Temperature>34 &#176;C</Current_Temperature>
    <Maximum_Temperature_During_Entire_Lifespan>49 &#176;C</Maximum_Temperature_During_Entire_Lifespan>
    <Health>89 %</Health>
    <Performance>100 %</Performance>
    <Estimated_Remaining_Lifetime>more than 1000 days</Estimated_Remaining_Lifetime>
    <Health_Text>The hard disk status is PERFECT. Problematic or weak sectors were not found.</Health_Text>
  </Physical_Disk_Information_Disk_HDD_0>
  <Physical_Disk_Information_Disk_SSD_1>
    <Disk_Device>/dev/sdb</Disk_Device>
    <Interface>S-ATA Gen3, 6 Gbps</Interface>
    <Disk_Model_ID>SSD 60GB</Disk_Model_ID>
    <Firmware_Revision>SBFM</Firmware_Revision>
    <Hard_Disk_Serial_Number></Hard_Disk_Serial_Number>
    <Total_Size>60022 MB</Total_Size>
    <Power_on_Time>44 hours</Power_on_Time>
    <Current_Temperature>30 &#176;C</Current_Temperature>
    <Health>100 %</Health>
    <Performance>100 %</Performance>
    <Estimated_Remaining_Lifetime>more than 1000 days</Estimated_Remaining_Lifetime>
    <Health_Text>The SSD status is PERFECT.</Health_Text>
  </Physical_Disk_Information_Disk_SSD_1>
</Hard_Disk_Sentinel>
"""


def test_parse_two_disks():
    disks = parse_xml(SAMPLE_XML)
    assert len(disks) == 2, f"expected 2 disks, got {len(disks)}"

    sda = disks[0]
    assert sda.device == "/dev/sda"
    assert sda.model == "TOSHIBA MQ01ABD032"
    assert sda.serial == "X5J7TABCS"
    assert sda.disk_type == DiskType.HDD
    assert abs(sda.size_gb - 305.245) < 0.01
    assert sda.health == 89
    assert sda.temp_current == 34
    assert sda.temp_max == 49
    assert sda.power_on_hours == 133 * 24 + 2
    assert sda.status == Status.PERFECT
    assert sda.identity == "X5J7TABCS"  # serial preferred

    sdb = disks[1]
    assert sdb.disk_type == DiskType.SSD
    assert sdb.serial == ""
    assert sdb.power_on_hours == 44
    # serial empty -> identity falls back to device (no wwn parsed here)
    assert sdb.identity == "/dev/sdb"
    print("OK test_parse_two_disks")


def test_empty_raises():
    try:
        parse_xml("")
    except HDSentinelParseError:
        print("OK test_empty_raises")
        return
    raise AssertionError("empty input should raise HDSentinelParseError")


def test_paths_enumeration():
    devs = paths.physical_block_devices()
    print(f"  physical_block_devices -> {devs}")
    assert isinstance(devs, list)
    for d in devs:
        meta = paths.sysfs_disk_meta(d)
        assert meta["device"] == f"/dev/{d}"
        assert meta["disk_type"] in ("HDD", "SSD", "NVMe", "Unknown")
        print(f"  {d}: {meta['disk_type']} {meta['size_gb']} GB model={meta['model']!r}")
    sm = paths.find_smartctl()
    print(f"  smartctl -> {sm}")
    print("OK test_paths_enumeration")


if __name__ == "__main__":
    test_parse_two_disks()
    test_empty_raises()
    test_paths_enumeration()
    print("\nALL PASSED")
