import unittest
from datetime import datetime, timezone

from wdw_core import (
    EvidenceReference,
    MemoryCandidate,
    MemoryKind,
    MemorySource,
    PublicEvidence,
    PublicMemory,
)


NOW = datetime(2026, 8, 14, 10, tzinfo=timezone.utc)


class MemoryContractTests(unittest.TestCase):
    def test_candidate_identity_is_stable_across_replay(self) -> None:
        source = MemorySource("mini-me", "observation-42")
        first = MemoryCandidate.create(
            occurred_at=NOW,
            observed_at=NOW,
            source=source,
            kind=MemoryKind.CONNECTION,
            significance="A durable relationship became visible.",
            headline="A relationship becomes visible",
            summary="A public-safe summary.",
            evidence_references=(EvidenceReference("Public page", "/projects/", True),),
        )
        retry = MemoryCandidate.create(
            occurred_at=NOW,
            observed_at=NOW,
            source=source,
            kind=MemoryKind.CONNECTION,
            significance="Changed evaluator wording does not change identity.",
            headline="Changed wording",
            summary="Changed summary.",
        )
        self.assertEqual(first.candidate_id, retry.candidate_id)

    def test_public_projection_is_an_explicit_allowlist(self) -> None:
        memory = PublicMemory(
            memory_id="mem_0123456789abcdef",
            slug="a-public-memory",
            occurred_at=NOW,
            published_at=NOW,
            kind=MemoryKind.MILESTONE,
            title="A public memory",
            summary="Only editorial projection fields cross the boundary.",
            source_label="Manual editorial review",
            source_type="editorial",
            theme="accountable systems",
            public_evidence=(PublicEvidence("Projects", "/projects/"),),
        )
        payload = memory.to_public_dict()
        self.assertNotIn("private_context", payload)
        self.assertNotIn("candidateId", payload)
        self.assertEqual(payload["publicationMode"], "manual")

    def test_private_evidence_link_fails_closed(self) -> None:
        memory = PublicMemory(
            memory_id="mem_0123456789abcdef",
            slug="bad-link",
            occurred_at=NOW,
            published_at=NOW,
            kind=MemoryKind.REFLECTION,
            title="Bad link",
            summary="This should not serialize.",
            source_label="Review",
            source_type="editorial",
            theme="privacy",
            public_evidence=(PublicEvidence("Private", "http://localhost:4321/private"),),
        )
        with self.assertRaises(ValueError):
            memory.to_public_dict()


if __name__ == "__main__":
    unittest.main()
