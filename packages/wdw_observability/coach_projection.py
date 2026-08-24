from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any


UNKNOWN = {"state": "unknown", "reason": "No direct Coach evidence was observed."}
_HM_KEYS = {
    "human_model_changes",
    "humanModelChanges",
    "human_model_change",
    "humanModelChange",
}


def _time(row: Mapping[str, Any]) -> datetime | None:
    for key in ("completed_at", "updated_at", "occurred_at", "observed_at", "started_at"):
        value = row.get(key)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is not None:
                return parsed
    return None


def _source(row: Mapping[str, Any]) -> str | None:
    for key in ("source_ref", "evidence_ref", "deep_link"):
        if isinstance(row.get(key), str) and row[key].strip():
            return str(row[key])
    return None


def _coach_record(row: Mapping[str, Any]) -> bool:
    return (
        row.get("resident_id") == "coach"
        or row.get("actor") == "coach"
        or row.get("operation") == "coach_morning_insight"
    )


def _explicit_human_model_changes(value: Any, *, path: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in _HM_KEYS:
                values = child if isinstance(child, (list, tuple)) else [child]
                changes.extend({"path": child_path, "change": item} for item in values)
            else:
                changes.extend(_explicit_human_model_changes(child, path=child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            changes.extend(_explicit_human_model_changes(child, path=f"{path}[{index}]"))
    return changes


def _timeline_entry(
    row: Mapping[str, Any], category: str, summary: str, *, detail: Any = None
) -> dict[str, Any]:
    timestamp = _time(row)
    return {
        "at": timestamp.isoformat() if timestamp else None,
        "category": category,
        "summary": summary,
        "detail": detail,
        "evidenceState": row.get("evidence_state", "unknown"),
        "sourceRef": _source(row),
        "raw": dict(row),
    }


def _activity_category(row: Mapping[str, Any]) -> str:
    text = " ".join(
        str(row.get(key, "")) for key in ("activity_kind", "summary", "outcome")
    ).lower()
    if any(word in text for word in ("reject", "conflict", "blocked")):
        return "conflict-or-rejection"
    if any(word in text for word in ("deliver", "send", "output", "message")):
        return "output-or-delivery"
    if any(word in text for word in ("input", "ingest", "received")):
        return "input"
    return "activity"


def build_coach_projection(
    records: Iterable[Mapping[str, Any]], *, now: datetime | None = None, window_hours: int = 24
) -> dict[str, Any]:
    """Build a read-only Coach view from canonical observability records."""
    now = now or datetime.now(UTC)
    window_start = now - timedelta(hours=window_hours)
    all_rows = [dict(row) for row in records]
    rows = [row for row in all_rows if _coach_record(row)]
    rows.sort(key=lambda row: _time(row) or datetime.min.replace(tzinfo=UTC), reverse=True)

    def in_window(row: Mapping[str, Any]) -> bool:
        timestamp = _time(row)
        return bool(
            timestamp is not None
            and window_start <= timestamp <= now + timedelta(minutes=5)
        )

    window_rows = [row for row in rows if in_window(row)]

    snapshots = [row for row in rows if row.get("kind") == "ResidentSnapshot"]
    activities = [row for row in rows if row.get("kind") == "MeaningfulActivity"]
    ingestions = [row for row in rows if row.get("kind") == "Ingestion"]
    mornings = [row for row in rows if row.get("kind") == "MorningInsightOperation"]
    window_mornings = [
        row for row in window_rows if row.get("kind") == "MorningInsightOperation"
    ]
    attention = [row for row in rows if row.get("kind") == "AttentionItem"]
    latest_snapshot = snapshots[0] if snapshots else None
    latest_activity = activities[0] if activities else None
    latest_ingestion = ingestions[0] if ingestions else None
    latest_morning = mornings[0] if mornings else None
    latest_window_morning = window_mornings[0] if window_mornings else None

    changes: list[dict[str, Any]] = []
    for row in window_rows:
        timestamp = _time(row)
        assert timestamp is not None
        for change in _explicit_human_model_changes(row):
            changes.append({**change, "at": timestamp.isoformat(), "sourceRef": _source(row)})

    timeline: list[dict[str, Any]] = []
    for row in window_rows:
        timestamp = _time(row)
        assert timestamp is not None
        kind = row.get("kind")
        if kind == "MeaningfulActivity":
            timeline.append(_timeline_entry(row, _activity_category(row), str(row.get("summary") or row.get("activity_kind") or "Coach activity"), detail=row.get("outcome")))
        elif kind == "Ingestion":
            timeline.append(_timeline_entry(row, "input-and-ingestion", f"{row.get('source_kind') or 'Input'} ingestion: {row.get('status', 'unknown')}", detail={"items": row.get("item_count"), "warnings": row.get("warnings"), "errors": row.get("errors")}))
        elif kind == "AttentionItem":
            timeline.append(_timeline_entry(row, "human-attention", str(row.get("summary") or row.get("reason") or "Human attention requested"), detail={"reason": row.get("reason"), "status": row.get("status")}))
        elif kind == "MorningInsightOperation":
            if any(row.get(key) for key in ("current_state", "recent_observations", "historical_context")):
                timeline.append(_timeline_entry(row, "interpretation-and-persistence", "Coach interpreted morning context", detail={key: row.get(key) for key in ("current_state", "recent_observations", "historical_context") if row.get(key)}))
            if row.get("prediction") or row.get("model"):
                timeline.append(_timeline_entry(row, "reasoning-model-and-prediction", "Coach produced model-backed reasoning or a prediction", detail={key: row.get(key) for key in ("prediction", "provider", "model", "model_version") if row.get(key)}))
            if row.get("insight"):
                timeline.append(_timeline_entry(row, "insight", "Coach produced a morning insight", detail=row.get("insight")))
            if any(row.get(key) for key in ("output_message_id", "delivery_id", "transport_message_id", "external_message_id", "delivery_status")):
                timeline.append(_timeline_entry(row, "output-and-delivery", f"Morning insight delivery: {row.get('delivery_status') or row.get('status') or 'unknown'}", detail={key: row.get(key) for key in ("output_message_id", "delivery_id", "transport_message_id", "external_message_id") if row.get(key)}))
            if row.get("failure") or row.get("warnings"):
                timeline.append(_timeline_entry(row, "warning-or-error", "Morning insight reported a warning or failure", detail={"warnings": row.get("warnings"), "failure": row.get("failure")}))
        for change in _explicit_human_model_changes(row):
            timeline.append(_timeline_entry(row, "human-model-change", "Human Model changed because of this input", detail=change))
    timeline.sort(key=lambda entry: entry.get("at") or "", reverse=True)

    model_evidence: list[dict[str, Any]] = []
    if latest_window_morning and (
        latest_window_morning.get("model") or latest_window_morning.get("provider")
    ):
        model_id = latest_window_morning.get("model")
        version = latest_window_morning.get("model_version")
        evidence = {
            "provider": latest_window_morning.get("provider"), "modelId": model_id,
            "version": version, "prediction": latest_window_morning.get("prediction"),
            "outcome": latest_window_morning.get("delivery_status") or latest_window_morning.get("status"),
            "metrics": UNKNOWN, "sourceRef": _source(latest_window_morning),
        }
        versions = [row for row in all_rows if row.get("kind") == "ModelVersion" and row.get("model_id") == model_id and (not version or row.get("version") == version)]
        if versions:
            model_version = versions[0]
            evidence["purpose"] = model_version.get("purpose")
            evidence["modelStatus"] = model_version.get("status")
        evaluations = [row for row in all_rows if row.get("kind") == "EvaluationRun" and row.get("model_id") == model_id and (not version or row.get("model_version") == version)]
        if evaluations:
            evaluation = sorted(evaluations, key=lambda row: _time(row) or datetime.min.replace(tzinfo=UTC), reverse=True)[0]
            evidence["metrics"] = {key: evaluation.get(key) for key in ("thought_count", "candidate_count", "reviewed_count", "mean_similarity", "precision_at_k", "median_similarity", "min_similarity", "max_similarity", "readiness") if evaluation.get(key) is not None}
            evidence["evaluationSourceRef"] = _source(evaluation)
        model_evidence.append(evidence)

    errors = [row for row in window_rows if row.get("failure") or row.get("errors") or row.get("status") in {"failed", "error"}]
    open_attention = [row for row in attention if row.get("status") == "open"]
    in_progress = bool(latest_snapshot and in_window(latest_snapshot) and latest_snapshot.get("state") in {"working", "thinking"}) or bool(latest_morning and in_window(latest_morning) and latest_morning.get("status") in {"pending", "running", "incomplete"})
    recent_result = next((entry for entry in timeline if entry["category"] in {"insight", "output-and-delivery"}), None)
    if errors:
        indicator = {"symbol": "error", "state": "error", "reason": "Coach evidence reports a failure or ingestion error.", "sourceRef": _source(errors[0])}
    elif open_attention:
        indicator = {"symbol": "?", "state": "needs-human", "reason": str(open_attention[0].get("reason") or open_attention[0].get("summary")), "sourceRef": _source(open_attention[0])}
    elif in_progress:
        indicator = {"symbol": "…", "state": "in-progress", "reason": "The latest direct Coach evidence is in progress.", "sourceRef": _source(latest_morning or latest_snapshot or {})}
    elif recent_result:
        indicator = {"symbol": "!", "state": "new-result", "reason": recent_result["summary"], "sourceRef": recent_result["sourceRef"]}
    else:
        indicator = {"symbol": "idle", "state": "idle", "reason": "No active or newly completed Coach work was observed in the window.", "sourceRef": None}

    return {
        "schema": "wdw.coach-resident.v1", "residentId": "coach", "displayName": "Coach",
        "generatedAt": now.isoformat(), "windowHours": window_hours, "windowStart": window_start.isoformat(),
        "detailLink": "/residents/coach", "indicator": indicator,
        "status": ({"state": latest_snapshot.get("state"), "summary": latest_snapshot.get("status_summary"), "sourceRef": _source(latest_snapshot)} if latest_snapshot else UNKNOWN),
        "lastMeaningfulActivity": ({"at": latest_activity.get("occurred_at"), "summary": latest_activity.get("summary"), "outcome": latest_activity.get("outcome"), "sourceRef": _source(latest_activity)} if latest_activity else UNKNOWN),
        "ingestion": (latest_ingestion if latest_ingestion else UNKNOWN),
        "insight": ({"value": latest_morning.get("insight"), "status": latest_morning.get("status"), "sourceRef": _source(latest_morning)} if latest_morning and latest_morning.get("insight") else UNKNOWN),
        "prediction": ({"value": latest_morning.get("prediction"), "sourceRef": _source(latest_morning)} if latest_morning and latest_morning.get("prediction") else UNKNOWN),
        "warnings": [
            warning
            for row in window_rows
            for warning in (
                row.get("warnings")
                if isinstance(row.get("warnings"), (list, tuple))
                else [row.get("warnings")]
                if row.get("warnings")
                else []
            )
        ],
        "errors": errors,
        "attention": open_attention,
        "humanModel": {"authority": "human-model", "readOnly": True, "changes": changes, "state": "known" if changes else "unknown", "reason": None if changes else "No explicit Human Model change was recorded; current-state context is not treated as a change."},
        "models": model_evidence or [UNKNOWN], "timeline": timeline,
    }
