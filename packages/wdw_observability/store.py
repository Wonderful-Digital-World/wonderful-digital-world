from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .contracts import ObservabilityRecord, ReviewDecision


class OperatorStore:
    """Durable operator projection history; never canonical resident state."""

    def __init__(self, path: str | Path = "wdw-command-center.sqlite3") -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS observability_records (
                    record_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'real'
                );
                CREATE INDEX IF NOT EXISTS records_kind_occurred
                    ON observability_records(kind, occurred_at DESC);
                CREATE TABLE IF NOT EXISTS review_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(observability_records)")}
            if "mode" not in columns:
                connection.execute("ALTER TABLE observability_records ADD COLUMN mode TEXT NOT NULL DEFAULT 'real'")
            fixture_ids = ("snapshot-mini-me", "snapshot-bridget", "snapshot-coach", "snapshot-banjo", "snapshot-human-model", "eval-reference", "activity-1", "ingestion-1")
            connection.executemany("UPDATE observability_records SET mode='fixture' WHERE record_id=?", ((item,) for item in fixture_ids))

    def append(self, record: ObservabilityRecord, *, mode: str = "real") -> bool:
        if mode not in {"real", "fixture"}:
            raise ValueError("mode must be real or fixture")
        if isinstance(record, ReviewDecision) and mode != "fixture" and not (
            record.canonical_owner == "mini-me" and record.read_only
        ):
            raise ValueError("Review decisions are canonically written by Mini Me; Command Center is read-only.")
        payload = json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO observability_records
                (record_id, kind, occurred_at, observed_at, payload, mode)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id,
                    type(record).__name__,
                    record.occurred_at.isoformat(),
                    record.observed_at.isoformat(),
                    payload,
                    mode,
                ),
            )
            if isinstance(record, ReviewDecision) and cursor.rowcount:
                connection.execute(
                    """INSERT INTO review_audit (decision_id, occurred_at, payload)
                    VALUES (?, ?, ?)""",
                    (record.record_id, record.occurred_at.isoformat(), payload),
                )
            return bool(cursor.rowcount)

    def append_many(self, records: Iterable[ObservabilityRecord], *, mode: str = "real") -> int:
        return sum(self.append(record, mode=mode) for record in records)

    def records(self, kind: str | None = None, limit: int = 100, *, mode: str = "real") -> list[dict[str, Any]]:
        if limit < 1 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")
        query = "SELECT kind, payload FROM observability_records WHERE mode = ?"
        params: list[Any] = [mode]
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            return [
                {"kind": row["kind"], **json.loads(row["payload"])}
                for row in connection.execute(query, params)
            ]

    def review_audit(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                json.loads(row["payload"])
                for row in connection.execute(
                    "SELECT payload FROM review_audit ORDER BY sequence"
                )
            ]
