from __future__ import annotations

from datetime import datetime, timezone

import pytest

from wdw_observability.adapters import (
    banjo_activity_records,
    bridget_ingestion_records,
    mini_me_review_evaluation_records,
)
from wdw_observability.contracts import (
    EvaluationRun,
    Ingestion,
    MeaningfulActivity,
    ReviewDecision,
    ReviewOutcome,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def test_reads_banjo_owned_activity_with_compute_history():
    records = banjo_activity_records(
        {
            "contractVersion": "1.0",
            "owner": "banjo",
            "eventId": "activity-1",
            "occurredAt": "2026-08-17T10:00:00Z",
            "actor": "banjo",
            "activityType": "engineering.work_item",
            "summary": "Implemented a repository boundary",
            "outcome": "completed",
            "links": {
                "workItem": "WP1",
                "model": None,
                "evaluations": [],
                "ingestion": None,
            },
            "evidenceLinks": ["commit:abc123"],
            "computeProvenance": {
                "provider": "openai",
                "model": "gpt-test",
                "attempts": 2,
                "latencyMs": 123,
                "cumulativeCost": None,
                "complexity": "medium",
                "risk": "low",
                "trace": "trace-1",
                "history": [{"attempt": 1}, {"attempt": 2}],
            },
        },
        NOW,
    )

    assert len(records) == 1
    activity = records[0]
    assert isinstance(activity, MeaningfulActivity)
    assert activity.canonical_owner == "banjo"
    assert activity.compute_provenance["history"] == [
        {"attempt": 1},
        {"attempt": 2},
    ]


def test_reads_bridget_owned_ingestion_without_inventing_counts():
    records = bridget_ingestion_records(
        {
            "contractVersion": "1.0",
            "owner": "bridget",
            "runs": [
                {
                    "contractVersion": "1.0",
                    "owner": "bridget",
                    "ingestionId": "run-1",
                    "source": {"type": "apple-health", "inputRefs": []},
                    "startedAt": "2026-08-17T10:00:00Z",
                    "completedAt": None,
                    "status": "running",
                    "counts": {"emitted": None, "loaded": None},
                    "freshness": {
                        "state": "known",
                        "asOf": "2026-08-17T10:00:00Z",
                    },
                    "processor": {"name": "apple-health", "version": None},
                    "schemaVersion": None,
                    "warnings": [],
                    "errors": [],
                    "provenance": {},
                }
            ],
        },
        NOW,
    )

    assert len(records) == 1
    ingestion = records[0]
    assert isinstance(ingestion, Ingestion)
    assert ingestion.canonical_owner == "bridget"
    assert ingestion.item_count is None
    assert ingestion.emitted_count is None
    assert ingestion.loaded_count is None


def test_reads_only_real_mini_me_reviews_when_evaluations_are_unavailable():
    records = mini_me_review_evaluation_records(
        {
            "contractVersion": "1.0",
            "owner": "mini-me",
            "generatedAt": "2026-08-17T10:00:00Z",
            "reviews": [
                {
                    "decisionId": "review-1",
                    "occurredAt": "2026-08-17T09:00:00Z",
                    "subjectId": "memory-1",
                    "requestId": "request-1",
                    "reviewer": "operator",
                    "outcome": "approved",
                    "note": "Verified",
                    "reviewKind": "artifact-lifecycle",
                    "subjectKind": "memory",
                }
            ],
            "evaluations": [],
            "evaluationAvailability": {
                "state": "unavailable",
                "reason": "No canonical evaluation-run store exists.",
            },
        },
        NOW,
    )

    assert not any(isinstance(record, EvaluationRun) for record in records)
    assert len(records) == 1
    review = records[0]
    assert isinstance(review, ReviewDecision)
    assert review.canonical_owner == "mini-me"
    assert review.read_only is True
    assert review.outcome is ReviewOutcome.APPROVED


def test_rejects_unknown_boundary_versions():
    with pytest.raises(ValueError, match="unsupported banjo"):
        banjo_activity_records(
            {"contractVersion": "2.0", "owner": "banjo"}, NOW
        )
