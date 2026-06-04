"""SQLite history manager.

Stores temperature/health history, periodic SMART snapshots, and the alert log.
The DB lives under the XDG data dir (``~/.local/share/diskmaster/diskmaster.db``)
so it survives config resets and stays out of the source tree.

One :class:`HistoryDB` instance owns one connection and is intended to be used
from a single thread (the GUI thread). Writes are tiny and infrequent (a handful
of rows every full-poll interval), so this needs no pooling.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from .models import DiskHistory, DiskInfo, SmartAttribute

_XDG_DATA = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
DATA_DIR = Path(_XDG_DATA) / "diskmaster"
DB_PATH = DATA_DIR / "diskmaster.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS disk_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    identity    TEXT    NOT NULL,
    device      TEXT,
    timestamp   INTEGER NOT NULL,
    temp        INTEGER,
    health      INTEGER,
    performance INTEGER
);
CREATE INDEX IF NOT EXISTS idx_history_identity
    ON disk_history(identity, timestamp);

CREATE TABLE IF NOT EXISTS smart_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    identity   TEXT    NOT NULL,
    timestamp  INTEGER NOT NULL,
    attr_id    INTEGER,
    attr_name  TEXT,
    raw_value  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_smart_identity
    ON smart_snapshots(identity, timestamp);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    identity     TEXT    NOT NULL,
    timestamp    INTEGER NOT NULL,
    alert_type   TEXT,
    message      TEXT,
    acknowledged INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(timestamp);

CREATE TABLE IF NOT EXISTS selftests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    identity    TEXT    NOT NULL,
    device      TEXT,
    test_type   TEXT,
    started_ts  INTEGER NOT NULL,
    finished_ts INTEGER,
    status      TEXT    NOT NULL DEFAULT 'running',   -- running/completed/aborted/error
    result      TEXT
);
CREATE INDEX IF NOT EXISTS idx_selftests_identity
    ON selftests(identity, started_ts);
"""


class HistoryDB:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DB_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def _now() -> int:
        return int(time.time())

    # ------------------------------------------------------------- recording --

    def record_disks(self, disks: list[DiskInfo], ts: int | None = None) -> int:
        """Append a history row per disk that has at least temp or health.

        Returns the number of rows written. Disks with neither value known
        (e.g. sysfs-only skeletons before a scan) are skipped.
        """
        ts = ts if ts is not None else self._now()
        rows = [
            (d.identity, d.device, ts, _nn(d.temp_current), _nn(d.health),
             _nn(d.performance))
            for d in disks
            if d.temp_current >= 0 or d.health >= 0
        ]
        if not rows:
            return 0
        self._conn.executemany(
            "INSERT INTO disk_history "
            "(identity, device, timestamp, temp, health, performance) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def record_smart(self, identity: str, attrs: list[SmartAttribute],
                     ts: int | None = None) -> int:
        ts = ts if ts is not None else self._now()
        rows = [(identity, ts, a.attr_id, a.name, a.raw_value) for a in attrs]
        if not rows:
            return 0
        self._conn.executemany(
            "INSERT INTO smart_snapshots "
            "(identity, timestamp, attr_id, attr_name, raw_value) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    # --------------------------------------------------------------- queries --

    def history(self, identity: str, since_ts: int | None = None,
                limit: int = 5000) -> list[DiskHistory]:
        """Temperature/health series for one disk, oldest first."""
        from datetime import datetime

        q = ("SELECT timestamp, temp, health, performance FROM disk_history "
             "WHERE identity = ?")
        args: list = [identity]
        if since_ts is not None:
            q += " AND timestamp >= ?"
            args.append(since_ts)
        q += " ORDER BY timestamp ASC LIMIT ?"
        args.append(limit)
        out = []
        for row in self._conn.execute(q, args):
            out.append(
                DiskHistory(
                    identity=identity,
                    timestamp=datetime.fromtimestamp(row["timestamp"]),
                    temp=row["temp"] if row["temp"] is not None else -1,
                    health=row["health"] if row["health"] is not None else -1,
                    performance=(row["performance"]
                                 if row["performance"] is not None else -1),
                )
            )
        return out

    def identities(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT identity FROM disk_history ORDER BY identity"
        )
        return [r["identity"] for r in rows]

    # ---------------------------------------------------------------- alerts --

    def add_alert(self, identity: str, alert_type: str, message: str,
                  ts: int | None = None) -> None:
        self._conn.execute(
            "INSERT INTO alerts (identity, timestamp, alert_type, message) "
            "VALUES (?, ?, ?, ?)",
            (identity, ts if ts is not None else self._now(), alert_type, message),
        )
        self._conn.commit()

    def recent_alerts(self, limit: int = 100,
                      include_acknowledged: bool = False) -> list[dict]:
        q = ("SELECT identity, timestamp, alert_type, message, acknowledged "
             "FROM alerts ")
        if not include_acknowledged:
            q += "WHERE acknowledged = 0 "
        q += "ORDER BY timestamp DESC LIMIT ?"
        return [dict(r) for r in self._conn.execute(q, (limit,))]

    def acknowledge_all(self) -> int:
        """Mark every alert acknowledged (audit trail stays in the table)."""
        cur = self._conn.execute("UPDATE alerts SET acknowledged = 1")
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------ self-tests --

    def selftest_start(self, identity: str, device: str, test_type: str,
                       ts: int | None = None) -> int:
        """Record a freshly launched self-test as 'running'.

        Any earlier still-'running' test for the same disk is marked 'aborted'
        (a new run supersedes it), so at most one running row exists per disk.
        Returns the new row id.
        """
        ts = ts if ts is not None else self._now()
        self._conn.execute(
            "UPDATE selftests SET status='aborted', finished_ts=? "
            "WHERE identity=? AND status='running'",
            (ts, identity),
        )
        cur = self._conn.execute(
            "INSERT INTO selftests "
            "(identity, device, test_type, started_ts, status) "
            "VALUES (?, ?, ?, ?, 'running')",
            (identity, device, test_type, ts),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def selftest_running(self, identity: str) -> dict | None:
        """The disk's currently-running self-test row, or None."""
        row = self._conn.execute(
            "SELECT * FROM selftests WHERE identity=? AND status='running' "
            "ORDER BY started_ts DESC LIMIT 1",
            (identity,),
        ).fetchone()
        return dict(row) if row else None

    def selftest_finish(self, identity: str, status: str = "completed",
                        result: str | None = None,
                        ts: int | None = None) -> bool:
        """Close the disk's running self-test. Returns True if one was open."""
        ts = ts if ts is not None else self._now()
        cur = self._conn.execute(
            "UPDATE selftests SET status=?, result=?, finished_ts=? "
            "WHERE identity=? AND status='running'",
            (status, result, ts, identity),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def selftest_recent(self, identity: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM selftests WHERE identity=? "
            "ORDER BY started_ts DESC LIMIT ?",
            (identity, limit),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- retention --

    def cleanup(self, retention_days: int) -> int:
        """Drop history/snapshots older than the retention window.

        Alerts are kept (they are an audit trail). Returns rows deleted.
        """
        if retention_days <= 0:
            return 0
        cutoff = self._now() - retention_days * 86400
        cur = self._conn.execute(
            "DELETE FROM disk_history WHERE timestamp < ?", (cutoff,)
        )
        deleted = cur.rowcount
        self._conn.execute(
            "DELETE FROM smart_snapshots WHERE timestamp < ?", (cutoff,)
        )
        self._conn.commit()
        return deleted

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


def _nn(v: int) -> int | None:
    """Map the model's -1 'unknown' sentinel to SQL NULL."""
    return None if v is None or v < 0 else v


__all__ = ["HistoryDB", "DB_PATH", "DATA_DIR"]
