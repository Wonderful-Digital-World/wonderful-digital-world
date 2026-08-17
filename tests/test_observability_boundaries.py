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


def test_reads_canonical_mini_me_evaluation_run_snapshot():
    records = mini_me_review_evaluation_records(
        {
            "contractVersion": "2.0",
            "owner": "mini-me",
            "generatedAt": "2026-08-17T10:00:00Z",
            "reviews": [],
            "evaluations": [
                {
                    "contractVersion": "2.0",
                    "evaluationRunId": "eval-1",
                    "evaluationName": "thought-intelligence-ranking",
                    "evaluationVersion": "1",
                    "purpose": "Evaluate ranking against complete human labels.",
                    "dataset": {
                        "id": "thought-intelligence-candidates",
                        "version": "dataset-v1",
                        "sourceCount": 72,
                        "candidateCount": 360,
                    },
                    "analysisVersions": ["thought-intelligence-v1"],
                    "models": [{"name": "text-embedding-3-small", "version": "1"}],
                    "evaluationCodeVersion": "mini-me@ef60403",
                    "evaluatedAt": "2026-08-17T09:00:00Z",
                    "reproducibility": {
                        "ks": [1, 3, 5],
                        "eligibility": "Complete labels through K.",
                        "sourceRef": "postgres://mini-me/evaluation-runs/eval-1",
                    },
                    "evidence": {
                        "thoughts": 72,
                        "candidates": 360,
                        "reviewed": 0,
                        "accepted": 0,
                        "rejected": 0,
                        "unsure": 0,
                    },
                    "scoreDistribution": {
                        "kind": "embedding-cosine-similarity",
                        "count": 360,
                        "min": 0.4,
                        "max": 0.9,
                        "mean": 0.728,
                        "bins": [{"lower": 0.4, "upper": 0.9, "count": 360}],
                        "interpretation": "Diagnostic only; not model quality.",
                    },
                    "rankBehavior": [
                        {
                            "rank": 1,
                            "candidates": 72,
                            "reviewed": 0,
                            "accepted": 0,
                            "rejected": 0,
                            "unsure": 0,
                            "meanScore": 0.81,
                        }
                    ],
                    "topCandidates": [
                        {
                            "analysisId": "analysis-1",
                            "sourceThoughtId": "thought-1",
                            "targetThoughtId": "thought-2",
                            "rank": 1,
                            "score": 0.88,
                            "reviewStatus": "unreviewed",
                        }
                    ],
                    "precisionAtK": {
                        key: {
                            "state": "unavailable",
                            "value": None,
                            "eligibleGroups": 0,
                            "reason": f"No source ranking has complete human labels through K={key}.",
                        }
                        for key in ("1", "3", "5")
                    },
                    "readiness": {
                        "state": "pending-human-review",
                        "verdict": "unavailable",
                        "reason": "No human relationship labels are available; model quality cannot be assessed.",
                    },
                    "limitations": ["Similarity is diagnostic and does not establish quality."],
                    "provenance": {
                        "owner": "mini-me",
                        "evidenceSource": "canonical-postgres-rows",
                    },
                }
            ],
            "evaluationAvailability": {"state": "available", "reason": None},
        },
        NOW,
    )

    assert len(records) == 1
    evaluation = records[0]
    assert isinstance(evaluation, EvaluationRun)
    assert evaluation.record_id == "eval-1"
    assert evaluation.contract_version == "2.0"
    assert evaluation.dataset["version"] == "dataset-v1"
    assert evaluation.precision_at_k["5"]["state"] == "unavailable"
    assert evaluation.readiness["state"] == "pending-human-review"
    assert evaluation.score_distribution["bins"][0]["count"] == 360
    assert evaluation.source_ref == "postgres://mini-me/evaluation-runs/eval-1"
    assert evaluation.top_candidates[0]["targetThoughtId"] == "thought-2"


def test_rejects_unknown_boundary_versions():
    with pytest.raises(ValueError, match="unsupported banjo"):
        banjo_activity_records(
            {"contractVersion": "2.0", "owner": "banjo"}, NOW
        )
