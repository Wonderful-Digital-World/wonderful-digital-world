from datetime import datetime, timedelta, timezone

from .contracts import (
    AttentionItem,
    AttentionState,
    EvaluationRun,
    EvidenceState,
    Ingestion,
    MeaningfulActivity,
    ResidentSnapshot,
    ResidentState,
)


def synthetic_records(now: datetime | None = None):
    """Clearly synthetic dogfood data matching the brief's reference evaluation."""
    current = now or datetime.now(timezone.utc)
    observed = current - timedelta(hours=30)
    residents = (
        ("mini-me", "Mini Me", ResidentState.ACTIVE, "Context synthesis is current."),
        ("bridget", "Bridget", ResidentState.NEEDS_ATTENTION, "One handoff needs review."),
        ("coach", "Coach", ResidentState.IDLE, "Fixture status."),
        ("banjo", "Banjo", ResidentState.IDLE, "Fixture status."),
    )
    records = [
        ResidentSnapshot(
            f"snapshot-{slug}", observed, observed, EvidenceState.KNOWN,
            slug, name, state, summary, observed - timedelta(hours=2),
        )
        for slug, name, state, summary in residents
    ]
    records.extend(
        [
            EvaluationRun(
                "eval-reference", observed, observed, EvidenceState.INSUFFICIENT,
                "memory-retrieval", "fixture-2026-08", 72, 360, 0, 0.728, None,
            ),
            AttentionItem(
                "attention-bridget-fixture", observed, observed, EvidenceState.KNOWN,
                "bridget", "haley", AttentionState.OPEN,
                "A fixture handoff is ready for operator review.", "handoff",
                "Review Bridget's fixture handoff.", observed, None,
                "fixture://bridget/handoff", "fixture://bridget", None,
                "/residents/bridget",
            ),
            MeaningfulActivity(
                "activity-1", observed, observed, EvidenceState.KNOWN,
                "mini-me", "synthesis", "A context synthesis completed.", "completed", None,
            ),
            Ingestion(
                "ingestion-1", observed, observed, EvidenceState.KNOWN,
                "bridget", "operator-export", 12, "complete",
            ),
        ]
    )
    return records
