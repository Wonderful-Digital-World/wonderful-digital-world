from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from wdw_observability.contracts import (
    EvaluationRun,
    EvidenceState,
    Ingestion,
    MeaningfulActivity,
    ResidentSnapshot,
    ResidentState,
)
from wdw_observability.overview import create_app
from wdw_observability.store import OperatorStore

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=2)


class CommandCenterOverviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "workspace"
        (self.workspace / "banjo").mkdir(parents=True)
        self.store = OperatorStore(self.root / "operator.sqlite3")

    def _records(self, observed_at: datetime = OLD) -> list[Any]:
        return [
            ResidentSnapshot(
                record_id="resident-banjo",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="banjo",
                display_name="Banjo Private",
                state=ResidentState.NEEDS_ATTENTION,
                status_summary="Private status",
                last_meaningful_activity_at=observed_at,
            ),
            MeaningfulActivity(
                record_id="activity-banjo",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="banjo",
                kind="delivery",
                summary="Shipped rhythm",
                outcome="complete",
                source_ref="https://example.test/activity",
            ),
            Ingestion(
                record_id="ingestion-bridget",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="bridget",
                source_kind="conversation-export",
                item_count=12,
                status="complete",
                completed_at=observed_at,
                source_details={"report": "https://example.test/ingestion"},
            ),
            EvaluationRun(
                record_id="evaluation-mini-me",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                model_id="mini-me",
                model_version="1",
                thought_count=100,
                candidate_count=10,
                reviewed_count=5,
                precision_at_k=0.8,
            ),
        ]

    def _request(
        self,
        path: str = "/overview",
        query: str = "view=private",
        *,
        scan_error: str | None = None,
    ) -> tuple[str, dict[str, str], bytes]:
        response: dict[str, Any] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            response["status"] = status
            response["headers"] = dict(headers)

        app = create_app(
            self.store,
            workspace=self.workspace,
            now_provider=lambda: NOW,
            scan_error=scan_error,
        )
        body = b"".join(
            app({"PATH_INFO": path, "QUERY_STRING": query}, start_response)
        )
        return response["status"], response["headers"], body

    def test_private_page_answers_the_wp3_operator_questions(self) -> None:
        self.store.append_many(self._records())

        status, headers, body = self._request()
        page = body.decode()

        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Cache-Control"], "no-store")
        for section in (
            "Needs Haley",
            "Residents",
            "Intelligence Summary",
            "System Health",
            "Recent Activity",
            "Recent Data Ingestions",
        ):
            self.assertIn(section, page)
        self.assertIn("Banjo Private", page)
        self.assertIn("Shipped rhythm", page)
        self.assertIn("conversation-export", page)
        self.assertIn("aging", page)
        self.assertIn((self.workspace / "banjo").resolve().as_uri(), page)

        _, _, api_body = self._request("/api/overview")
        overview = json.loads(api_body)
        self.assertEqual(overview["schema"], "wdw.operator-overview.v1")
        self.assertEqual(overview["intelligenceSummary"]["precisionAtK"], 0.8)
        self.assertEqual(len(overview["systemHealth"]), 4)

    def test_public_preview_uses_delayed_allowlisted_real_projection(self) -> None:
        self.store.append_many(self._records())

        _, _, body = self._request("/api/overview", "view=public")
        public = json.loads(body)

        self.assertTrue(public["available"])
        self.assertEqual(public["schema"], "wdw.systems.v1")
        self.assertEqual(public["releaseDelayHours"], 24.0)
        self.assertEqual(public["residents"]["needsAttention"], 1)
        serialized = json.dumps(public)
        for private_value in ("Banjo Private", "Private status", "Shipped rhythm"):
            self.assertNotIn(private_value, serialized)

    def test_public_preview_is_explicit_when_real_data_is_still_delayed(self) -> None:
        self.store.append_many(self._records(NOW - timedelta(hours=1)))

        _, _, body = self._request("/overview", "view=public")
        page = body.decode()

        self.assertIn("Delayed projection not available yet", page)
        self.assertIn("24.0 hours", page)
        self.assertNotIn("Banjo Private", page)

    def test_empty_and_scan_failure_states_remain_truthful_and_escaped(self) -> None:
        _, _, body = self._request(scan_error="broken <source>")
        page = body.decode()

        self.assertIn("Source refresh failed", page)
        self.assertIn("broken &lt;source&gt;", page)
        self.assertIn("No resident snapshots observed", page)
        self.assertIn("No meaningful activity has been observed", page)
        self.assertIn("No data ingestion runs have been observed", page)
        self.assertNotIn("broken <source>", page)

    def test_fixture_rows_never_appear_in_either_view(self) -> None:
        self.store.append_many(self._records(), mode="fixture")

        _, _, private_body = self._request()
        _, _, public_body = self._request("/api/overview", "view=public")

        self.assertNotIn("Banjo Private", private_body.decode())
        public = json.loads(public_body)
        self.assertFalse(public["available"])


if __name__ == "__main__":
    unittest.main()
