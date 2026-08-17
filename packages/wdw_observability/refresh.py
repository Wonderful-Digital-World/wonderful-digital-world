from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from .adapters import workspace_records
from .contracts import ObservabilityRecord
from .store import OperatorStore


RecordSource = Callable[[Path], Iterable[ObservabilityRecord]]


class ProjectionRefresher:
    """Refresh real workspace projections at a bounded request-time cadence."""

    def __init__(
        self,
        store: OperatorStore,
        workspace: Path,
        *,
        interval_seconds: float = 5.0,
        source: RecordSource = workspace_records,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.store = store
        self.workspace = workspace
        self.interval_seconds = interval_seconds
        self.source = source
        self._lock = threading.Lock()
        self._next_due = 0.0
        self._last_attempt: datetime | None = None
        self._last_success: datetime | None = None
        self._last_error: str | None = None

    def refresh(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now < self._next_due:
            return False
        if not self._lock.acquire(blocking=False):
            return False
        try:
            now = time.monotonic()
            if not force and now < self._next_due:
                return False
            self._next_due = now + self.interval_seconds
            self._last_attempt = datetime.now(timezone.utc)
            try:
                self.store.reconcile(self.source(self.workspace), mode="real")
            except Exception as exc:  # surfaced in projection status; server remains useful
                self._last_error = f"{type(exc).__name__}: {exc}"
                return False
            self._last_success = datetime.now(timezone.utc)
            self._last_error = None
            return True
        finally:
            self._lock.release()

    def status(self) -> dict[str, object]:
        if self._last_error:
            state = "error"
        elif self._last_success is None:
            state = "stale"
        else:
            age = (datetime.now(timezone.utc) - self._last_success).total_seconds()
            state = "stale" if age > self.interval_seconds * 2 else "current"
        return {
            "state": state,
            "lastAttemptAt": self._last_attempt.isoformat() if self._last_attempt else None,
            "lastSuccessAt": self._last_success.isoformat() if self._last_success else None,
            "error": self._last_error,
            "intervalSeconds": self.interval_seconds,
        }
