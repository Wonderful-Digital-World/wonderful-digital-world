from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wdw_observability.app import create_app
from wdw_observability.contracts import (
    AttentionItem,
    AttentionState,
    EvidenceState,
    MeaningfulActivity,
    ResidentSnapshot,
    ResidentState,
)
from wdw_observability.projections import private_overview
from wdw_observability.refresh import ProjectionRefresher
from wdw_observability.sample import synthetic_records
from wdw_observability.store import OperatorStore


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def snapshot(
    summary: str = "Ready",
    *,
    occurred_at: datetime = NOW,
    state: ResidentState = ResidentState.ACTIVE,
) -> ResidentSnapshot:
    return ResidentSnapshot(
        record_id="resident-bridget",
        occurred_at=occurred_at,
        observed_at=occurred_at,
        evidence_state=EvidenceState.KNOWN,
        resident_id="bridget",
        display_name="Bridget",
        state=state,
        status_summary=summary,
        last_meaningful_activity_at=occurred_at,
    )


def activity(summary: str = "Delivered", *, occurred_at: datetime = NOW) -> MeaningfulActivity:
    return MeaningfulActivity(
        record_id="activity-fixed",
        occurred_at=occurred_at,
        observed_at=occurred_at,
        evidence_state=EvidenceState.KNOWN,
        resident_id="bridget",
        kind="delivery",
        summary=summary,
        outcome="completed",
        source_ref="inbox/bridget",
    )


def attention(
    record_id: str,
    status: AttentionState = AttentionState.OPEN,
) -> AttentionItem:
    return AttentionItem(
        record_id=record_id,
        occurred_at=NOW,
        observed_at=NOW,
        evidence_state=EvidenceState.KNOWN,
        resident_id="bridget",
        owner="Haley",
        status=status,
        reason="Workout data needs review",
        category="workout",
        summary="Review Bridget's workout warning",
        updated_at=NOW,
        resolved_at=NOW if status == AttentionState.RESOLVED else None,
        evidence_ref="evidence/workout-1",
        source_ref="health/bridget",
        related_work_item_id="work-bridget-1",
        deep_link="/residents/bridget/attention/workout",
    )


def request_json(app, path: str = "/api/overview") -> dict:
    status = []

    def start_response(value, _headers):
        status.append(value)

    body = b"".join(app({"PATH_INFO": path, "REQUEST_METHOD": "GET"}, start_response))
    if status != ["200 OK"]:
        raise AssertionError(status)
    import json

    return json.loads(body)


class CommandCenterCorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.store = OperatorStore(Path(self.tempdir.name) / "operator.sqlite3")

    def test_activity_preserves_record_and_domain_discriminators(self) -> None:
        self.assertTrue(self.store.append(activity()))

        row = self.store.records()[0]
        self.assertEqual(row["kind"], "MeaningfulActivity")
        self.assertEqual(row["activity_kind"], "delivery")

    def test_mutable_projection_updates_but_immutable_history_does_not(self) -> None:
        self.assertTrue(self.store.append(snapshot("First")))
        self.assertTrue(self.store.append(snapshot("Second", occurred_at=NOW + timedelta(minutes=1))))
        self.assertTrue(self.store.append(activity("First event")))
        self.assertFalse(
            self.store.append(activity("Rewritten event", occurred_at=NOW + timedelta(minutes=1)))
        )

        rows = self.store.records()
        residents = [row for row in rows if row["kind"] == "ResidentSnapshot"]
        activities = [row for row in rows if row["kind"] == "MeaningfulActivity"]
        self.assertEqual(len(residents), 1)
        self.assertEqual(residents[0]["status_summary"], "Second")
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["summary"], "First event")

    def test_reconcile_removes_stale_mutable_rows_and_keeps_history(self) -> None:
        self.store.reconcile([snapshot("First"), attention("attention-open"), activity()])
        self.store.reconcile([snapshot("Current", occurred_at=NOW + timedelta(minutes=1))])

        rows = self.store.records()
        self.assertEqual(
            [row["status_summary"] for row in rows if row["kind"] == "ResidentSnapshot"],
            ["Current"],
        )
        self.assertEqual([row for row in rows if row["kind"] == "AttentionItem"], [])
        self.assertEqual(len([row for row in rows if row["kind"] == "MeaningfulActivity"]), 1)

    def test_needs_haley_is_derived_only_from_open_attention_items(self) -> None:
        needs_state = snapshot(state=ResidentState.NEEDS_ATTENTION)
        self.store.reconcile(
            [
                needs_state,
                attention("open"),
                attention("resolved", AttentionState.RESOLVED),
            ]
        )

        overview = private_overview(self.store.records(), NOW)
        self.assertEqual([item["record_id"] for item in overview["needsHaley"]], ["open"])

    def test_fixture_purge_removes_contamination_without_deleting_real_rows(self) -> None:
        self.store.reconcile(synthetic_records(NOW), mode="fixture")
        self.store.append(snapshot(), mode="real")

        self.assertGreater(self.store.purge_fixtures(), 0)
        self.assertEqual(self.store.records(mode="fixture"), [])
        real = self.store.records(mode="real")
        self.assertEqual([row["resident_id"] for row in real if row["kind"] == "ResidentSnapshot"], ["bridget"])

    def test_running_app_observes_refresh_without_restart(self) -> None:
        source_state = {"summary": "First"}

        def source(_workspace: Path):
            return [snapshot(source_state["summary"])]

        refresher = ProjectionRefresher(
            self.store,
            Path(self.tempdir.name),
            source=source,
            interval_seconds=60,
        )
        refresher.refresh(force=True)
        app = create_app(self.store, mode="real", refresher=refresher)
        self.assertEqual(request_json(app)["residents"][0]["status_summary"], "First")

        source_state["summary"] = "Second"
        refresher.refresh(force=True)
        refreshed = request_json(app)
        self.assertEqual(refreshed["residents"][0]["status_summary"], "Second")
        self.assertEqual(refreshed["projection"]["state"], "current")

    def test_refresh_failures_are_visible(self) -> None:
        def broken_source(_workspace: Path):
            raise RuntimeError("source unavailable")

        refresher = ProjectionRefresher(
            self.store,
            Path(self.tempdir.name),
            source=broken_source,
            interval_seconds=60,
        )
        self.assertFalse(refresher.refresh(force=True))
        self.assertEqual(refresher.status()["state"], "error")
        self.assertIn("source unavailable", refresher.status()["error"])

    def test_store_closes_connections_for_reads_and_writes(self) -> None:
        opened = []
        original_connect = self.store._connect

        class TrackedConnection:
            def __init__(self, connection):
                self.connection = connection
                self.closed = False

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def __enter__(self):
                self.connection.__enter__()
                return self

            def __exit__(self, *args):
                return self.connection.__exit__(*args)

            def close(self):
                self.closed = True
                self.connection.close()

        def tracked_connect():
            connection = TrackedConnection(original_connect())
            opened.append(connection)
            return connection

        self.store._connect = tracked_connect
        self.store.append(snapshot())
        self.store.records()
        self.store.review_audit()
        self.assertTrue(opened)
        self.assertTrue(all(connection.closed for connection in opened))


if __name__ == "__main__":
    unittest.main()
