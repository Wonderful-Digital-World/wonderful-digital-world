"""Durable replay protection and evidence/proposal record for sandbox turns."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path


class ReplayConflict(RuntimeError):
    pass


class RequestInProgress(RuntimeError):
    pass


class TurnStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS coach_turns (
                request_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, trace_id TEXT NOT NULL,
                evidence_json TEXT NOT NULL, invocation_json TEXT NOT NULL,
                raw_response_json TEXT, public_response_json TEXT, proposals_json TEXT,
                state TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.connection.commit()

    def reserve(self, request_id: str, request_hash: str, trace_id: str, evidence: dict, invocation: dict) -> dict | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT request_hash, state, public_response_json FROM coach_turns WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row:
                if row[0] != request_hash:
                    raise ReplayConflict("requestId was already used with different input")
                if row[1] == "complete":
                    return json.loads(row[2])
                if row[1] == "pending":
                    raise RequestInProgress("requestId is already in progress")
                self.connection.execute(
                    "UPDATE coach_turns SET trace_id=?, evidence_json=?, invocation_json=?, "
                    "raw_response_json=NULL, public_response_json=NULL, proposals_json=NULL, state='pending' "
                    "WHERE request_id=?",
                    (trace_id, _json(evidence), _json(invocation), request_id),
                )
            else:
                self.connection.execute(
                    "INSERT INTO coach_turns(request_id, request_hash, trace_id, evidence_json, invocation_json, state) VALUES(?,?,?,?,?,?)",
                    (request_id, request_hash, trace_id, _json(evidence), _json(invocation), "pending"),
                )
            self.connection.commit()
            return None

    def complete(self, request_id: str, raw: dict, public: dict, proposals: list[dict]) -> None:
        with self._lock:
            cursor = self.connection.execute(
                "UPDATE coach_turns SET raw_response_json=?, public_response_json=?, proposals_json=?, state='complete' "
                "WHERE request_id=? AND state='pending'",
                (_json(raw), _json(public), _json(proposals), request_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("requestId is not pending")
            self.connection.commit()

    def fail(self, request_id: str) -> None:
        with self._lock:
            self.connection.execute(
                "UPDATE coach_turns SET state='failed' WHERE request_id=? AND state='pending'", (request_id,)
            )
            self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
