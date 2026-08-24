from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from wdw_observability.contracts import (
    AttentionItem,
    AttentionState,
    EvaluationRun,
    EvidenceState,
    Ingestion,
    MeaningfulActivity,
    ModelVersion,
    MorningInsightOperation,
    ResidentSnapshot,
    ResidentState,
)
from wdw_observability.activity import activity_log_path, append_resident_activity
from socketserver import ThreadingMixIn

from wdw_observability.overview import ProjectionRefresher, ThreadingWSGIServer, create_app
from wdw_observability.store import OperatorStore

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=2)


class CommandCenterServerTests(unittest.TestCase):
    def test_server_handles_browser_connections_concurrently(self) -> None:
        self.assertTrue(issubclass(ThreadingWSGIServer, ThreadingMixIn))
        self.assertTrue(ThreadingWSGIServer.daemon_threads)


def _canonical_evaluation(
    record_id: str,
    occurred_at: datetime,
    *,
    dataset_version: str = "dataset-v1",
    precision_values: dict[str, float] | None = None,
    source_ref: str = "postgres://mini-me/evaluation-runs/current",
) -> EvaluationRun:
    precision_at_k: dict[str, dict[str, Any]] = {}
    for key in ("1", "3", "5"):
        if precision_values and key in precision_values:
            precision_at_k[key] = {
                "state": "available",
                "value": precision_values[key],
                "eligibleGroups": 4,
                "reason": None,
            }
        else:
            precision_at_k[key] = {
                "state": "unavailable",
                "value": None,
                "eligibleGroups": 0,
                "reason": f"No source ranking has complete human labels through K={key}.",
            }
    reviewed = 15 if precision_values else 0
    readiness = (
        {
            "state": "ready",
            "verdict": "measured",
            "reason": "At least one precision-at-K measure has a completely human-labeled source ranking.",
        }
        if precision_values
        else {
            "state": "pending-human-review",
            "verdict": "unavailable",
            "reason": "No human relationship labels are available; model quality cannot be assessed.",
        }
    )
    return EvaluationRun(
        record_id=record_id,
        occurred_at=occurred_at,
        observed_at=occurred_at,
        evidence_state=EvidenceState.KNOWN,
        model_id="text-embedding-3-small",
        model_version="1",
        thought_count=72,
        candidate_count=360,
        reviewed_count=reviewed,
        mean_similarity=0.728,
        min_similarity=0.4,
        max_similarity=0.9,
        precision_at_k=precision_at_k,
        score_distribution={
            "kind": "embedding-cosine-similarity",
            "count": 360,
            "min": 0.4,
            "max": 0.9,
            "mean": 0.728,
            "bins": (
                {"lower": 0.4, "upper": 0.65, "count": 40},
                {"lower": 0.65, "upper": 0.9, "count": 320},
            ),
            "interpretation": "Diagnostic candidate-score distribution; not a model-quality measure.",
        },
        rank_behavior=(
            {
                "rank": 1,
                "candidates": 72,
                "reviewed": 4 if precision_values else 0,
                "accepted": 3 if precision_values else 0,
                "rejected": 1 if precision_values else 0,
                "unsure": 0,
                "meanScore": 0.81,
            },
        ),
        analysis_version="thought-intelligence-v1",
        readiness=readiness,
        top_candidates=(
            {
                "analysisId": "analysis-1",
                "sourceThoughtId": "thought-1",
                "targetThoughtId": "thought-2",
                "rank": 1,
                "score": 0.88,
                "reviewStatus": "accepted" if precision_values else "unreviewed",
            },
        ),
        source_ref=source_ref,
        canonical_owner="mini-me",
        read_only=True,
        contract_version="2.0",
        evaluation_name="thought-intelligence-ranking",
        evaluation_version="1",
        purpose="Evaluate candidate relationship ranking against complete human labels.",
        dataset={
            "id": "thought-intelligence-candidates",
            "version": dataset_version,
            "sourceCount": 72,
            "candidateCount": 360,
        },
        analysis_versions=("thought-intelligence-v1",),
        models=({"name": "text-embedding-3-small", "version": "1"},),
        evaluation_code_version="mini-me@ef60403",
        reproducibility={
            "ks": [1, 3, 5],
            "eligibility": "A source contributes to P@K only when ranks 1 through K have human labels.",
            "sourceRef": source_ref,
        },
        evidence={
            "thoughts": 72,
            "candidates": 360,
            "reviewed": reviewed,
            "accepted": 3 if precision_values else 0,
            "rejected": 1 if precision_values else 0,
            "unsure": 0,
        },
        limitations=("Similarity is diagnostic and does not establish quality.",),
        provenance={
            "owner": "mini-me",
            "evidenceSource": "canonical-postgres-rows",
            "scoreMeaning": "embedding-cosine-similarity",
            "humanLabels": "latest-candidate-status-backed-by-append-only-review-history",
        },
    )


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
            AttentionItem(
                record_id="attention-banjo",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="banjo",
                owner="haley",
                status=AttentionState.OPEN,
                reason="Operator decision required",
                category="decision",
                summary="Review Banjo's current request",
                updated_at=observed_at,
                evidence_ref="https://example.test/evidence",
                source_ref="https://example.test/attention",
                related_work_item_id="work-banjo",
                deep_link="/residents/banjo",
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
        app = create_app(
            self.store,
            workspace=self.workspace,
            now_provider=lambda: NOW,
            scan_error=scan_error,
        )
        return self._call(app, path, query)

    def _call(
        self, app: Any, path: str = "/overview", query: str = "view=private"
    ) -> tuple[str, dict[str, str], bytes]:
        response: dict[str, Any] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            response["status"] = status
            response["headers"] = dict(headers)

        body = b"".join(app({"PATH_INFO": path, "QUERY_STRING": query}, start_response))
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
            "Models",
            "Morning Insights",
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
        self.assertEqual(overview["models"]["availability"]["state"], "unavailable")
        self.assertEqual(len(overview["systemHealth"]), 5)

    def test_models_requires_a_canonical_run_and_exposes_unavailable_precision(self) -> None:
        self.store.append_many(
            self._records() + [_canonical_evaluation("eval-current", NOW - timedelta(hours=1))]
        )

        _, _, api_body = self._request("/api/overview")
        overview = json.loads(api_body)
        models = overview["models"]

        self.assertEqual(models["latest"]["runId"], "eval-current")
        self.assertEqual(models["latest"]["readiness"]["state"], "pending-human-review")
        for key in ("1", "3", "5"):
            measure = models["latest"]["precisionAtK"][key]
            self.assertEqual(measure["state"], "unavailable")
            self.assertIn("complete human labels", measure["reason"])

        _, _, page_body = self._request()
        page = page_body.decode()
        for expected in (
            "Models",
            "pending-human-review",
            "P@1",
            "Unavailable",
            "No human relationship labels are available",
            "Score distribution",
            "Rank behavior",
            "Top candidates",
            "Provenance",
        ):
            self.assertIn(expected, page)

    def test_models_compares_only_compatible_canonical_runs(self) -> None:
        baseline = _canonical_evaluation(
            "eval-baseline",
            OLD + timedelta(hours=2),
            precision_values={"1": 0.7, "3": 0.6, "5": 0.5},
            source_ref="postgres://mini-me/evaluation-runs/baseline",
        )
        current = _canonical_evaluation(
            "eval-current",
            OLD + timedelta(hours=3),
            precision_values={"1": 0.8, "3": 0.7, "5": 0.6},
        )
        incompatible = _canonical_evaluation(
            "eval-other-dataset",
            OLD + timedelta(hours=1),
            dataset_version="dataset-v2",
            precision_values={"1": 0.9, "3": 0.8, "5": 0.7},
        )
        self.store.append_many(self._records() + [incompatible, baseline, current])

        _, _, api_body = self._request("/api/overview")
        history = json.loads(api_body)["models"]["history"]

        self.assertEqual(history["compatibleRuns"], 2)
        self.assertEqual(history["excludedRuns"], 1)
        self.assertEqual(history["baselineRunId"], "eval-baseline")
        self.assertEqual(history["comparison"]["1"]["state"], "available")
        self.assertAlmostEqual(history["comparison"]["1"]["delta"], 0.1)

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

    def test_coach_projection_covers_commissioning_flows(self) -> None:
        observed_at = NOW - timedelta(minutes=10)
        self.store.append_many([
            ResidentSnapshot(
                record_id="resident-coach",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="coach",
                display_name="Coach",
                state=ResidentState.WORKING,
                status_summary="Synthesizing recovery evidence.",
                last_meaningful_activity_at=observed_at,
            ),
            MeaningfulActivity(
                record_id="activity-coach-message",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="coach",
                kind="received-input",
                summary="Accepted Haley's recovery input",
                outcome="persisted",
                source_ref="message://coach/recovery",
            ),
            Ingestion(
                record_id="ingestion-coach-macrofactor",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                resident_id="coach",
                source_kind="MacroFactor",
                item_count=3,
                status="complete",
                completed_at=observed_at,
                source_details={"sourceRef": "macro-factor://recovery"},
            ),
            MorningInsightOperation(
                record_id="morning-coach-recovery",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                occurrence_id="morning-2026-08-17",
                status="completed",
                stages=("load-context", "reason", "persist", "deliver"),
                insight={"headline": "Recovery is constrained"},
                evidence={"inputs": ["MacroFactor", "message"]},
                personalization={"focus": "recovery"},
                current_state={
                    "human_model_changes": [{
                        "field": "recovery.status",
                        "before": "unknown",
                        "after": "strained",
                        "because": "MacroFactor recovery input",
                    }]
                },
                recent_observations={"recovery": "strained"},
                historical_context={"baseline": "normal"},
                prediction={"plannedTraining": "easy", "outcome": "accepted"},
                provider="openai",
                model="coach-recovery-v1",
                model_version="2",
                output_message_id="message-output-1",
                delivery_id="delivery-1",
                delivery_status="delivered",
                source_ref="human-model://morning/2026-08-17",
            ),
            ModelVersion(
                record_id="model-coach-recovery-v2",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                model_id="coach-recovery-v1",
                version="2",
                purpose="Turn recovery evidence into planned training.",
                status="active",
            ),
            EvaluationRun(
                record_id="evaluation-coach-recovery-v2",
                occurred_at=observed_at,
                observed_at=observed_at,
                evidence_state=EvidenceState.KNOWN,
                model_id="coach-recovery-v1",
                model_version="2",
                thought_count=8,
                candidate_count=3,
                reviewed_count=3,
                precision_at_k=0.9,
                readiness="ready",
                source_ref="evaluation://coach-recovery-v1/2",
            ),
        ])

        status, _, api_body = self._request("/api/residents/coach", "")
        projection = json.loads(api_body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(projection["residentId"], "coach")
        self.assertEqual(projection["status"]["state"], "working")
        self.assertEqual(projection["ingestion"]["source_kind"], "MacroFactor")
        self.assertEqual(projection["insight"]["value"]["headline"], "Recovery is constrained")
        self.assertEqual(projection["prediction"]["value"]["plannedTraining"], "easy")
        self.assertEqual(projection["humanModel"]["authority"], "human-model")
        self.assertTrue(projection["humanModel"]["readOnly"])
        self.assertEqual(
            projection["humanModel"]["changes"][0]["change"]["field"],
            "recovery.status",
        )
        self.assertEqual(projection["models"][0]["modelId"], "coach-recovery-v1")
        self.assertEqual(projection["models"][0]["metrics"]["precision_at_k"], 0.9)
        categories = {entry["category"] for entry in projection["timeline"]}
        self.assertTrue({
            "input",
            "input-and-ingestion",
            "interpretation-and-persistence",
            "human-model-change",
            "reasoning-model-and-prediction",
            "insight",
            "output-and-delivery",
        }.issubset(categories))

        _, _, detail_body = self._request("/residents/coach", "")
        detail = detail_body.decode()
        for expected in ("Human Model is authoritative", "24-hour", "<details", "MacroFactor"):
            self.assertIn(expected, detail)

    def test_coach_activity_refreshes_in_the_same_process(self) -> None:
        refreshed_at = datetime.now(UTC)
        path = activity_log_path(self.workspace)
        append_resident_activity(
            path,
            resident_id="coach",
            state="working",
            summary="First Coach activity",
            occurred_at=refreshed_at,
        )
        refresher = ProjectionRefresher(
            self.store, self.workspace, interval_seconds=0.001
        )
        app = create_app(
            self.store,
            workspace=self.workspace,
            now_provider=lambda: datetime.now(UTC),
            refresher=refresher,
        )

        _, _, first_body = self._call(app, "/api/residents/coach", "")
        first = json.loads(first_body)
        self.assertEqual(first["status"]["state"], "working")
        self.assertEqual(first["status"]["summary"], "First Coach activity")

        append_resident_activity(
            path,
            resident_id="coach",
            state="waiting",
            summary="Second Coach activity",
            occurred_at=datetime.now(UTC),
        )
        time.sleep(0.01)
        _, _, second_body = self._call(app, "/api/residents/coach", "")
        second = json.loads(second_body)
        self.assertEqual(second["status"]["state"], "waiting")
        self.assertEqual(second["status"]["summary"], "Second Coach activity")


if __name__ == "__main__":
    unittest.main()
