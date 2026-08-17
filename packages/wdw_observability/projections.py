from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


class ProjectionNotReady(RuntimeError):
    pass


PUBLIC_DELAY = timedelta(hours=24)
PUBLIC_SCHEMA = "wdw.systems.v1"

_SENSITIVE_KEYS = frozenset(
    {
        "activity",
        "activities",
        "candidate_id",
        "email",
        "external_id",
        "health",
        "name",
        "note",
        "payload",
        "resident_id",
        "source_ref",
        "url",
    }
)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("projection timestamps must be timezone-aware")
    return parsed


def private_overview(records: Iterable[Mapping[str, Any]], generated_at: datetime) -> dict[str, Any]:
    rows = list(records)
    residents_by_id: dict[str, Mapping[str, Any]] = {}
    for row in (item for item in rows if item["kind"] == "ResidentSnapshot"):
        residents_by_id.setdefault(str(row.get("resident_id")), row)
    residents = list(residents_by_id.values())
    evaluations = [row for row in rows if row["kind"] == "EvaluationRun"]
    activities = [row for row in rows if row["kind"] == "MeaningfulActivity"][:8]
    ingestions = [row for row in rows if row["kind"] == "Ingestion"][:8]
    attention = [row for row in residents if row.get("state") == "needs-attention"]
    return {
        "schema": "wdw.operator-overview.v1",
        "generatedAt": generated_at.isoformat(),
        "needsHaley": attention,
        "residents": residents,
        "intelligence": evaluations,
        "health": {
            "state": "unknown" if not residents else ("partial" if any(row.get("evidence_state") != "known" for row in residents) else "known"),
            "residentCount": len(residents),
        },
        "recentActivity": activities,
        "recentIngestions": ingestions,
    }


def public_systems_projection(
    private: Mapping[str, Any],
    *,
    now: datetime | None = None,
    delay: timedelta = PUBLIC_DELAY,
) -> dict[str, Any]:
    """Create the only supported public shape from a private overview."""
    generated_at = _parse(str(private["generatedAt"]))
    current = now or datetime.now(timezone.utc)
    release_at = generated_at + delay
    if current < release_at:
        raise ProjectionNotReady(f"projection is releasable at {release_at.isoformat()}")

    residents = list(private.get("residents", []))
    evaluations = list(private.get("intelligence", []))
    latest_eval = evaluations[0] if evaluations else {}
    raw_reviewed = latest_eval.get("reviewed_count")
    reviewed = int(raw_reviewed) if raw_reviewed is not None else None
    precision = latest_eval.get("precision_at_k") if reviewed not in (None, 0) else None
    precision_state = "unknown" if reviewed is None else (
        "insufficient-evidence" if reviewed == 0 else ("known" if precision is not None else "unknown")
    )
    result = {
        "schema": PUBLIC_SCHEMA,
        "generatedAt": current.isoformat(),
        "sourceObservedAt": generated_at.isoformat(),
        "releaseDelayHours": delay.total_seconds() / 3600,
        "state": private.get("health", {}).get("state", "unknown"),
        "residents": {
            "total": len(residents),
            "active": sum(row.get("state") == "active" for row in residents),
            "needsAttention": sum(row.get("state") == "needs-attention" for row in residents),
        },
        "intelligence": {
            "thoughts": latest_eval.get("thought_count"),
            "candidates": latest_eval.get("candidate_count"),
            "reviewed": reviewed,
            "meanSimilarity": latest_eval.get("mean_similarity"),
            "precisionAtK": precision,
            "precisionAtKState": precision_state,
        },
    }
    assert_public_shape(result)
    return result


def assert_public_shape(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS:
                raise ValueError(f"sensitive public projection field: {'.'.join((*path, str(key)))}")
            assert_public_shape(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_public_shape(child, (*path, str(index)))
