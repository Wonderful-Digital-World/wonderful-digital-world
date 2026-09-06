"""Bounded, deliberately low-cardinality edge audit records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from logging import Formatter, Logger, getLogger
from logging.handlers import RotatingFileHandler
from pathlib import Path


_FIELDS = ("timestamp", "traceId", "tool", "outcome", "httpStatus")


class AuditLog:
    def __init__(self, path: Path, *, max_bytes: int = 1_000_000, backups: int = 3) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger: Logger = getLogger(f"wdw.coach_edge.audit.{id(self)}")
        self.logger.setLevel("INFO")
        self.logger.propagate = False
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        handler.setFormatter(Formatter("%(message)s"))
        self.logger.addHandler(handler)

    def write(self, *, trace_id: str, tool: str, outcome: str, http_status: int) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "traceId": trace_id,
            "tool": tool,
            "outcome": outcome,
            "httpStatus": http_status,
        }
        assert tuple(record) == _FIELDS
        self.logger.info(json.dumps(record, separators=(",", ":"), sort_keys=False))

    def close(self) -> None:
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
