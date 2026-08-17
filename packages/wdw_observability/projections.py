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
    attention = [
        row
        for row in rows
        if row["kind"] == "AttentionItem" and row.get("status") == "open"
    ]
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


def _precision_items(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key in ("1", "3", "5"):
        item = value.get(key)
        if isinstance(item, Mapping):
            result[key] = {
                "state": item.get("state", "unavailable"),
                "value": item.get("value"),
                "eligibleGroups": item.get("eligibleGroups", 0),
                "reason": item.get("reason"),
            }
    return result


def _compatibility_key(run: Mapping[str, Any]) -> tuple[Any, ...]:
    dataset = run.get("dataset") if isinstance(run.get("dataset"), Mapping) else {}
    reproducibility = (
        run.get("reproducibility") if isinstance(run.get("reproducibility"), Mapping) else {}
    )
    models = run.get("models") if isinstance(run.get("models"), (list, tuple)) else []
    model_key = tuple(
        (str(model.get("name")), str(model.get("version")))
        for model in models
        if isinstance(model, Mapping)
    )
    return (
        run.get("evaluation_name"),
        run.get("evaluation_version"),
        run.get("purpose"),
        dataset.get("id"),
        dataset.get("version"),
        tuple(run.get("analysis_versions") or ()),
        model_key,
        run.get("evaluation_code_version"),
        tuple(reproducibility.get("ks") or ()),
        reproducibility.get("eligibility"),
    )


def models_experience(evaluations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Project exact canonical evaluation snapshots into the private Models view."""
    runs = sorted(
        (
            row
            for row in evaluations
            if row.get("contract_version") == "2.0"
            and row.get("evaluation_name")
            and isinstance(row.get("dataset"), Mapping)
        ),
        key=lambda row: str(row.get("occurred_at", "")),
        reverse=True,
    )
    if not runs:
        return {
            "availability": {
                "state": "unavailable",
                "reason": "No canonical Mini Me evaluation-run snapshot is available.",
            },
            "latest": None,
            "history": None,
        }

    latest = runs[0]
    compatible = [run for run in runs if _compatibility_key(run) == _compatibility_key(latest)]
    baseline = compatible[1] if len(compatible) > 1 else None
    current_precision = _precision_items(latest.get("precision_at_k"))
    baseline_precision = _precision_items(baseline.get("precision_at_k")) if baseline else {}
    comparison: dict[str, dict[str, Any]] = {}
    for key in ("1", "3", "5"):
        current = current_precision.get(key, {})
        previous = baseline_precision.get(key, {})
        current_value = current.get("value")
        previous_value = previous.get("value")
        if (
            baseline
            and current.get("state") == "available"
            and previous.get("state") == "available"
            and current_value is not None
            and previous_value is not None
        ):
            comparison[key] = {
                "state": "available",
                "current": current_value,
                "previous": previous_value,
                "delta": float(current_value) - float(previous_value),
                "reason": None,
            }
        else:
            reason = current.get("reason")
            if not baseline:
                reason = "No earlier compatible evaluation run is available."
            elif current.get("state") == "available":
                reason = previous.get("reason") or "The baseline P@K value is unavailable."
            comparison[key] = {
                "state": "unavailable",
                "current": current_value,
                "previous": previous_value,
                "delta": None,
                "reason": reason or "Human labels are insufficient for this K.",
            }

    return {
        "availability": {"state": "available", "reason": None},
        "latest": {
            "runId": latest.get("record_id"),
            "evaluatedAt": latest.get("occurred_at"),
            "evaluationName": latest.get("evaluation_name"),
            "evaluationVersion": latest.get("evaluation_version"),
            "purpose": latest.get("purpose"),
            "dataset": latest.get("dataset"),
            "analysisVersions": latest.get("analysis_versions"),
            "models": latest.get("models"),
            "evaluationCodeVersion": latest.get("evaluation_code_version"),
            "reproducibility": latest.get("reproducibility"),
            "evidence": latest.get("evidence"),
            "scoreDistribution": latest.get("score_distribution"),
            "rankBehavior": latest.get("rank_behavior"),
            "topCandidates": latest.get("top_candidates"),
            "precisionAtK": current_precision,
            "readiness": latest.get("readiness"),
            "limitations": latest.get("limitations"),
            "provenance": latest.get("provenance"),
        },
        "history": {
            "compatibleRuns": len(compatible),
            "excludedRuns": len(runs) - len(compatible),
            "baselineRunId": (
                baseline.get("record_id") if baseline else None
            ),
            "comparison": comparison,
        },
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
    raw_precision = latest_eval.get("precision_at_k")
    if isinstance(raw_precision, Mapping):
        precision = None
        has_available_precision = any(
            isinstance(item, Mapping) and item.get("state") == "available"
            for item in raw_precision.values()
        )
    else:
        precision = raw_precision if reviewed not in (None, 0) else None
        has_available_precision = precision is not None
    if isinstance(raw_precision, Mapping):
        precision_state = "known" if has_available_precision else "insufficient-evidence"
    else:
        precision_state = "unknown" if reviewed is None else (
            "insufficient-evidence" if reviewed == 0 else ("known" if has_available_precision else "unknown")
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
            "needsAttention": len(private.get("needsHaley", [])),
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
