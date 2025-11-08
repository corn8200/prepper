"""Metrics persistence to SQLite for observability."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict

from .signals import SurgeResult
from .sources.base import SourceResult


class MetricsStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                ended_at TEXT,
                duration_s REAL,
                dry_run INTEGER
            );
            CREATE TABLE IF NOT EXISTS fetch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                provider TEXT,
                location_id TEXT,
                result_count INTEGER,
                ok INTEGER,
                latency_ms INTEGER,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS surge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                location_id TEXT,
                count INTEGER,
                baseline REAL,
                factor REAL,
                domains INTEGER,
                tripped INTEGER
            );
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                run_id TEXT,
                location_id TEXT,
                category TEXT,
                priority INTEGER,
                title TEXT,
                reason TEXT,
                channels TEXT,
                delivered_push INTEGER,
                delivered_email INTEGER,
                ts TEXT
            );
            """
        )

    def record_run_start(self, run_id: str, started_at: datetime, dry_run: bool) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, started_at, dry_run) VALUES (?, ?, ?)",
            (run_id, started_at.isoformat(), int(dry_run)),
        )
        self.conn.commit()

    def record_run_end(self, run_id: str, ended_at: datetime, duration_s: float) -> None:
        self.conn.execute(
            "UPDATE runs SET ended_at = ?, duration_s = ? WHERE run_id = ?",
            (ended_at.isoformat(), duration_s, run_id),
        )
        self.conn.commit()

    def record_fetch(self, run_id: str, result: SourceResult) -> None:
        self.conn.execute(
            "INSERT INTO fetch(run_id, provider, location_id, result_count, ok, latency_ms, error) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                result.provider,
                result.location_id,
                len(result.items),
                int(result.ok),
                result.latency_ms or 0,
                result.error or "",
            ),
        )
        self.conn.commit()

    def record_surge(self, run_id: str, surge: SurgeResult) -> None:
        self.conn.execute(
            "INSERT INTO surge(run_id, location_id, count, baseline, factor, domains, tripped) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                surge.location_id,
                surge.count,
                surge.baseline,
                surge.factor,
                surge.distinct_domains,
                int(surge.tripped),
            ),
        )
        self.conn.commit()

    def record_alert(self, run_id: str, alert_id: str, location_id: str, decision: Dict, channels: Dict[str, bool], timestamp: datetime) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO alerts(alert_id, run_id, location_id, category, priority, title, reason, channels, delivered_push, delivered_email, ts)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                alert_id,
                run_id,
                location_id,
                decision.get("category"),
                decision.get("priority"),
                decision.get("title"),
                decision.get("reason"),
                json.dumps(channels),
                int(channels.get("pushover", False)),
                int(channels.get("email", False)),
                timestamp.isoformat(),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
