from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Status(StrEnum):
    IMPLEMENTED = "implemented"
    DOGFOOD_READY = "dogfood-ready"
    EXPERIMENTAL = "experimental"
    PLANNED = "planned"
    ASPIRATIONAL = "aspirational"
    INTENTIONALLY_REJECTED = "intentionally rejected"


class Outcome(StrEnum):
    ACTED = "acted"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class Artifact:
    """Immutable received evidence with enough provenance to audit its origin."""

    artifact_id: str
    media_type: str
    body: bytes
    source: str
    external_id: str
    received_at: datetime = field(default_factory=utc_now)

    @property
    def digest(self) -> str:
        return sha256(self.body).hexdigest()


@dataclass(slots=True)
class WorkItem:
    """Durable request for bounded work; it is not canonical domain truth."""

    kind: str
    recipient: str
    artifact_id: str
    work_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utc_now)
    context: Mapping[str, Any] = field(default_factory=dict)
    outcome: Outcome | None = None
    reason: str | None = None

    def finish(self, outcome: Outcome, reason: str) -> None:
        if self.outcome is not None:
            raise ValueError("a completed WorkItem is immutable")
        self.outcome = outcome
        self.reason = reason
