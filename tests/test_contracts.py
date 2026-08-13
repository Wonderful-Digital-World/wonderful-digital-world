import unittest
from datetime import datetime, timezone

from wdw_core import Artifact, Outcome
from wdw_inbox import Inbox
from wdw_interfaces import Projection
from wdw_tools import Authority, AuthorityDenied


class ContractTests(unittest.TestCase):
    def test_transport_replay_is_idempotent(self) -> None:
        inbox = Inbox()
        first = Artifact("a-1", "text/plain", b"hello", "demo", "evt-1")
        retry = Artifact("a-2", "text/plain", b"changed", "demo", "evt-1")
        self.assertTrue(inbox.receive(first).created)
        receipt = inbox.receive(retry)
        self.assertFalse(receipt.created)
        self.assertEqual(receipt.artifact.artifact_id, "a-1")

    def test_route_requires_persisted_artifact(self) -> None:
        with self.assertRaises(KeyError):
            Inbox().route("missing", recipient="coach", kind="review")

    def test_work_outcome_is_final(self) -> None:
        inbox = Inbox()
        inbox.receive(Artifact("a-1", "text/plain", b"hello", "demo", "evt-1"))
        work = inbox.route("a-1", recipient="coach", kind="review")
        work.finish(Outcome.ABSTAINED, "outside domain")
        with self.assertRaises(ValueError):
            work.finish(Outcome.ACTED, "changed mind")

    def test_authority_is_explicit(self) -> None:
        authority = Authority("coach", frozenset({"fitness:propose"}))
        authority.require("fitness:propose")
        with self.assertRaises(AuthorityDenied):
            authority.require("calendar:write")

    def test_projection_is_viewer_bounded(self) -> None:
        projection = Projection(
            "1.0", "p-1", datetime.now(timezone.utc), "rev-7", 60,
            "main-square", {"attention": []}, frozenset({"human"})
        )
        self.assertIs(projection.for_viewer("human"), projection)
        with self.assertRaises(PermissionError):
            projection.for_viewer("anonymous")


if __name__ == "__main__":
    unittest.main()
