"""Replaceable, authorized projections of persistent state."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Projection:
    contract_version: str
    projection_id: str
    generated_at: datetime
    source_revision: str
    freshness_seconds: int
    place: str
    payload: Mapping[str, Any]
    authorized_for: frozenset[str]

    def for_viewer(self, viewer: str) -> "Projection":
        if viewer not in self.authorized_for:
            raise PermissionError("viewer is not authorized for this projection")
        return self
