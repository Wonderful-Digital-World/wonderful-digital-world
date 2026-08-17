from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

from .contracts import AttentionItem, ObservabilityRecord, ResidentSnapshot, ReviewDecision


MUTABLE_RECORD_TYPES = (ResidentSnapshot, AttentionItem)
MUTABLE_KINDS = {record_type.__name__ for record_type in MUTABLE_RECORD_TYPES}


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
        with closing(self._connect()) as connection, connection:
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
            fixture_ids = ("snapshot-mini-me", "snapshot-bridget", "snapshot-coach", "snapshot-banjo", "snapshot-human-model", "attention-bridget-fixture", "eval-reference", "activity-1", "ingestion-1")
            connection.executemany("UPDATE observability_records SET mode='fixture' WHERE record_id=?", ((item,) for item in fixture_ids))

    @staticmethod
    def _validate(record: ObservabilityRecord, mode: str) -> None:
        if mode not in {"real", "fixture"}:
            raise ValueError("mode must be real or fixture")
        if isinstance(record, ReviewDecision) and mode != "fixture" and not (
            record.canonical_owner == "mini-me" and record.read_only
        ):
            raise ValueError("Review decisions are canonically written by Mini Me; Command Center is read-only.")

    @staticmethod
    def _write(connection: sqlite3.Connection, record: ObservabilityRecord, mode: str) -> bool:
        payload = json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
        kind = type(record).__name__
        existing = connection.execute(
            "SELECT kind, mode FROM observability_records WHERE record_id = ?",
            (record.record_id,),
        ).fetchone()
        if existing and (existing["kind"] != kind or existing["mode"] != mode):
            raise ValueError(f"record_id {record.record_id!r} already belongs to another kind or mode")
        if existing and kind in MUTABLE_KINDS:
            connection.execute(
                """UPDATE observability_records
                SET occurred_at = ?, observed_at = ?, payload = ?
                WHERE record_id = ?""",
                (
                    record.occurred_at.isoformat(),
                    record.observed_at.isoformat(),
                    payload,
                    record.record_id,
                ),
            )
            return True
        if existing:
            return False
        connection.execute(
                """INSERT INTO observability_records
                (record_id, kind, occurred_at, observed_at, payload, mode)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id,
                    kind,
                    record.occurred_at.isoformat(),
                    record.observed_at.isoformat(),
                    payload,
                    mode,
                ),
            )
        if isinstance(record, ReviewDecision):
            connection.execute(
                    """INSERT INTO review_audit (decision_id, occurred_at, payload)
                    VALUES (?, ?, ?)""",
                    (record.record_id, record.occurred_at.isoformat(), payload),
                )
        return True

    def append(self, record: ObservabilityRecord, *, mode: str = "real") -> bool:
        self._validate(record, mode)
        with closing(self._connect()) as connection, connection:
            return self._write(connection, record, mode)

    def append_many(self, records: Iterable[ObservabilityRecord], *, mode: str = "real") -> int:
        return sum(self.append(record, mode=mode) for record in records)

    def reconcile(self, records: Iterable[ObservabilityRecord], *, mode: str = "real") -> int:
        """Atomically refresh mutable projections while retaining immutable history."""
        materialized = list(records)
        for record in materialized:
            self._validate(record, mode)
        mutable_ids = {
            kind: {record.record_id for record in materialized if type(record).__name__ == kind}
            for kind in MUTABLE_KINDS
        }
        with closing(self._connect()) as connection, connection:
            changed = sum(self._write(connection, record, mode) for record in materialized)
            for kind, record_ids in mutable_ids.items():
                if record_ids:
                    placeholders = ",".join("?" for _ in record_ids)
                    connection.execute(
                        f"DELETE FROM observability_records WHERE mode = ? AND kind = ? AND record_id NOT IN ({placeholders})",
                        (mode, kind, *sorted(record_ids)),
                    )
                else:
                    connection.execute(
                        "DELETE FROM observability_records WHERE mode = ? AND kind = ?",
                        (mode, kind),
                    )
            return changed

    def purge_fixtures(self) -> int:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM review_audit WHERE decision_id IN (SELECT record_id FROM observability_records WHERE mode = 'fixture')"
            )
            cursor = connection.execute("DELETE FROM observability_records WHERE mode = 'fixture'")
            return cursor.rowcount

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
        with closing(self._connect()) as connection:
            return [
                self._decode(row)
                for row in connection.execute(query, params)
            ]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"])
        if row["kind"] == "MeaningfulActivity" and "kind" in payload:
            payload.setdefault("activity_kind", payload.pop("kind"))
        payload["kind"] = row["kind"]
        return payload

    def review_audit(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return [
                json.loads(row["payload"])
                for row in connection.execute(
                    "SELECT payload FROM review_audit ORDER BY sequence"
                )
            ]
