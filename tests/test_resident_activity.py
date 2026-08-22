from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from wdw_observability.activity import activity_log_path, append_resident_activity
from wdw_observability.adapters import load_resident_activity, resident_activity_records, workspace_records
from wdw_observability.contracts import EvidenceState, ResidentState


NOW = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)


def event(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "wdw.resident-activity.v1", "eventId": "evt-1", "runId": "run-1",
        "residentId": "coach", "state": "thinking", "occurredAt": "2026-08-21T07:58:00Z",
        "summary": "Comparing recovery with the baseline.",
        "evidenceReferences": ["metric:recovery:2026-08-21"],
    }
    value.update(overrides)
    return value


def test_newest_runtime_event_is_current_truth() -> None:
    records = resident_activity_records([
        event(), event(eventId="evt-2", state="waiting", occurredAt="2026-08-21T07:59:00Z"),
    ], NOW)
    assert records[0].record_id == "evt-2"
    assert records[0].state is ResidentState.WAITING
    assert records[0].evidence_state is EvidenceState.KNOWN


def test_expired_runtime_event_becomes_stale_and_offline() -> None:
    records = resident_activity_records(
        [event(occurredAt="2026-08-21T07:30:00Z")], NOW, timedelta(minutes=15),
    )
    assert records[0].state is ResidentState.OFFLINE
    assert records[0].evidence_state is EvidenceState.STALE
    assert records[0].status_summary == "Runtime activity signal expired."


@pytest.mark.parametrize(("field", "value"), [
    ("state", "active"), ("residentId", "unknown"), ("occurredAt", "yesterday"),
    ("summary", ""), ("evidenceReferences", "metric:one"),
])
def test_invalid_activity_contract_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        resident_activity_records([event(**{field: value})], NOW)


def test_workspace_fallbacks_use_canonical_offline_state(tmp_path: Path) -> None:
    records = workspace_records(tmp_path)

    assert {record.resident_id for record in records} == {
        "bridget",
        "banjo",
        "coach",
        "mini-me",
    }
    assert {record.state for record in records} == {ResidentState.OFFLINE}


def test_shared_emitter_round_trips_all_residents(tmp_path: Path) -> None:
    path = activity_log_path(tmp_path)
    for resident_id in ("bridget", "coach", "mini-me", "banjo"):
        append_resident_activity(
            path, resident_id=resident_id, state="working",
            summary=f"{resident_id} is running the integration check.",
            evidence_references=["test:e2e"], run_id="run-e2e",
            occurred_at=NOW,
        )

    records = load_resident_activity(path, NOW)
    assert {record.resident_id for record in records} == {
        "bridget", "coach", "mini-me", "banjo",
    }
    assert {record.state for record in records} == {ResidentState.WORKING}


def test_shared_emitter_rejects_invalid_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not available at runtime"):
        append_resident_activity(
            activity_log_path(tmp_path), resident_id="coach", state="active", summary="Bad state.",
        )
