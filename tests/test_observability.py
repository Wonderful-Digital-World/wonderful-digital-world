import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from wdw_observability.app import create_app
from wdw_observability.contracts import EvaluationRun, EvidenceState, ReviewDecision, ReviewOutcome
from wdw_observability.export_public import releasable_records
from wdw_observability.projections import ProjectionNotReady, assert_public_shape, private_overview, public_systems_projection
from wdw_observability.sample import synthetic_records
from wdw_observability.store import OperatorStore


NOW = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)


class ObservabilityTests(unittest.TestCase):
    def test_precision_is_unavailable_without_reviewed_labels(self):
        evaluation = EvaluationRun("eval", NOW, NOW, EvidenceState.INSUFFICIENT, "model", "v1", 72, 360, 0, 0.728, None)
        self.assertIsNone(evaluation.precision_at_k)
        self.assertEqual(evaluation.precision_at_k_state, EvidenceState.INSUFFICIENT)

    def test_store_is_idempotent_and_review_audit_is_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OperatorStore(Path(directory) / "operator.sqlite3")
            decision = ReviewDecision("review-1", NOW, NOW, EvidenceState.KNOWN, "eval", "candidate", "haley", ReviewOutcome.RELEVANT, "synthetic")
            with self.assertRaises(ValueError):
                store.append(decision)
            self.assertTrue(store.append(decision, mode="fixture"))
            self.assertFalse(store.append(decision, mode="fixture"))
            self.assertEqual(len(store.review_audit()), 1)

    def test_public_projection_enforces_delay_and_allowlist(self):
        observed = NOW - timedelta(hours=25)
        records = [{"kind": type(record).__name__, **record.to_dict()} for record in synthetic_records(observed)]
        private = private_overview(records, observed)
        with self.assertRaises(ProjectionNotReady):
            public_systems_projection(private, now=observed + timedelta(hours=23))
        public = public_systems_projection(private, now=NOW)
        serialized = json.dumps(public)
        self.assertNotIn("display_name", serialized)
        self.assertNotIn("source_ref", serialized)
        self.assertEqual(public["intelligence"]["precisionAtKState"], "insufficient-evidence")
        self.assertIsNone(public["intelligence"]["precisionAtK"])
        with self.assertRaises(ValueError):
            assert_public_shape({"resident_id": "private"})

    def test_public_projection_marks_missing_precision_unknown_after_reviews(self):
        observed = NOW - timedelta(hours=25)
        records = [{"kind": type(record).__name__, **record.to_dict()} for record in synthetic_records(observed)]
        evaluation = next(record for record in records if record["kind"] == "EvaluationRun")
        evaluation["reviewed_count"] = 1
        evaluation["precision_at_k"] = None
        public = public_systems_projection(private_overview(records, observed), now=NOW)
        self.assertEqual(public["intelligence"]["precisionAtKState"], "unknown")
        self.assertIsNone(public["intelligence"]["precisionAtK"])

    def test_public_export_excludes_each_record_until_its_delay_expires(self):
        old = {"occurred_at": (NOW - timedelta(hours=25)).isoformat(), "record_id": "old"}
        fresh = {"occurred_at": (NOW - timedelta(hours=1)).isoformat(), "record_id": "fresh"}
        eligible, source_time = releasable_records(
            [old, fresh], now=NOW, delay=timedelta(hours=24)
        )
        self.assertEqual(eligible, [old])
        self.assertEqual(source_time, NOW - timedelta(hours=25))

    def test_private_routes_and_private_api(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(OperatorStore(Path(directory) / "operator.sqlite3"))
            statuses = []
            response = b"".join(app({"PATH_INFO": "/models"}, lambda status, headers: statuses.append(status)))
            self.assertEqual(statuses, ["200 OK"])
            self.assertIn(b"Unavailable", response)
            statuses.clear()
            payload = b"".join(app({"PATH_INFO": "/api/overview"}, lambda status, headers: statuses.append(status)))
            overview = json.loads(payload)
            self.assertEqual(overview["schema"], "wdw.operator-overview.v1")
            self.assertEqual(overview["health"]["state"], "unknown")

    def test_world_route_keeps_embed_mounted_while_service_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                OperatorStore(Path(directory) / "operator.sqlite3"),
                world_url="http://127.0.0.1:3000/rooms",
            )
            statuses = []
            with patch("wdw_observability.app._is_online", return_value=False) as is_online:
                response = b"".join(
                    app(
                        {"PATH_INFO": "/world"},
                        lambda status, headers: statuses.append(status),
                    )
                )

            self.assertEqual(statuses, ["200 OK"])
            is_online.assert_called_once_with("http://127.0.0.1:3000/api/health")
            self.assertIn(b'src="http://127.0.0.1:3000/rooms?mode=display"', response)
            self.assertIn(b"starting or temporarily unavailable", response)
            self.assertNotIn(b"The world is not running", response)


if __name__ == "__main__":
    unittest.main()
