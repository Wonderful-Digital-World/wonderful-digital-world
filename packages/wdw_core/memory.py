"""Typed memory contracts shared by producers and public projections.

The candidate and decision types are private workflow records. ``PublicMemory``
is the deliberately small, allowlisted boundary that may leave the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


PUBLIC_MEMORY_SCHEMA_VERSION = "1.0"


class MemoryKind(StrEnum):
    MILESTONE = "milestone"
    CONNECTION = "connection"
    PRACTICE = "practice"
    RELEASE = "release"
    REFLECTION = "reflection"


class MemorySensitivity(StrEnum):
    PUBLIC = "public"
    REVIEW = "review"
    RESTRICTED = "restricted"


class PublicationRecommendation(StrEnum):
    PUBLISH = "publish"
    REVIEW = "review"
    ABSTAIN = "abstain"


class PublicationState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("memory timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_memory_id(namespace: str, *parts: str) -> str:
    """Return a stable opaque id for replay-safe candidate creation."""

    material = "\x1f".join((namespace, *parts)).encode()
    return f"{namespace}_{sha256(material).hexdigest()[:20]}"


@dataclass(frozen=True, slots=True)
class MemorySource:
    system: str
    record_id: str
    actor: str | None = None
    operation: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    label: str
    href: str
    public: bool = False


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """Private proposal from a domain owner; never a publishable object."""

    candidate_id: str
    occurred_at: datetime
    observed_at: datetime
    source: MemorySource
    kind: MemoryKind
    significance: str
    headline: str
    summary: str
    evidence_references: tuple[EvidenceReference, ...]
    related_entity_references: tuple[str, ...]
    sensitivity: MemorySensitivity
    publication_recommendation: PublicationRecommendation
    correlation_id: str | None = None
    supersedes: str | None = None
    reconciled_by: str | None = None
    private_context: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        occurred_at: datetime,
        observed_at: datetime,
        source: MemorySource,
        kind: MemoryKind,
        significance: str,
        headline: str,
        summary: str,
        evidence_references: Sequence[EvidenceReference] = (),
        related_entity_references: Sequence[str] = (),
        sensitivity: MemorySensitivity = MemorySensitivity.REVIEW,
        publication_recommendation: PublicationRecommendation = PublicationRecommendation.REVIEW,
        correlation_id: str | None = None,
        private_context: Mapping[str, Any] | None = None,
    ) -> "MemoryCandidate":
        candidate_id = stable_memory_id(
            "memc", source.system, source.record_id, _utc_iso(occurred_at)
        )
        return cls(
            candidate_id=candidate_id,
            occurred_at=occurred_at,
            observed_at=observed_at,
            source=source,
            kind=kind,
            significance=significance,
            headline=headline,
            summary=summary,
            evidence_references=tuple(evidence_references),
            related_entity_references=tuple(related_entity_references),
            sensitivity=sensitivity,
            publication_recommendation=publication_recommendation,
            correlation_id=correlation_id,
            private_context=private_context or {},
        )


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    decision_id: str
    candidate_id: str
    policy_version: str
    state: PublicationState
    reasons: tuple[str, ...]
    reviewed_by: str
    decided_at: datetime
    sanitization: tuple[str, ...] = ()
    public_memory_id: str | None = None


@dataclass(frozen=True, slots=True)
class PublicEvidence:
    label: str
    href: str

    def validate(self) -> None:
        if not self.label.strip():
            raise ValueError("public evidence requires a label")
        parsed = urlparse(self.href)
        is_local = self.href.startswith("/") and not self.href.startswith("//")
        is_https = parsed.scheme == "https" and bool(parsed.netloc)
        if not (is_local or is_https):
            raise ValueError("public evidence must be a local route or HTTPS URL")
        lowered = self.href.lower()
        if any(token in lowered for token in ("localhost", "127.0.0.1", "private", ".git")):
            raise ValueError("private or development links cannot be public evidence")


@dataclass(frozen=True, slots=True)
class PublicMemory:
    memory_id: str
    slug: str
    occurred_at: datetime
    published_at: datetime
    kind: MemoryKind
    title: str
    summary: str
    source_label: str
    source_type: str
    theme: str
    editorial_weight: str = "standard"
    cluster_id: str | None = None
    related_projects: tuple[str, ...] = ()
    related_writing: tuple[str, ...] = ()
    public_evidence: tuple[PublicEvidence, ...] = ()
    tags: tuple[str, ...] = ()
    publication_mode: str = "manual"
    schema_version: str = PUBLIC_MEMORY_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != PUBLIC_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported public memory schema version")
        if not self.memory_id.startswith("mem_"):
            raise ValueError("public memory ids must be opaque mem_ identifiers")
        if not self.slug or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in self.slug):
            raise ValueError("public memory slug is invalid")
        if self.source_type not in {"editorial", "project", "resident", "system"}:
            raise ValueError("unsupported public memory source type")
        if self.editorial_weight not in {"feature", "standard", "note"}:
            raise ValueError("unsupported editorial weight")
        if self.publication_mode != "manual":
            raise ValueError("WP5 public memories require manual approval")
        for value in (self.title, self.summary, self.source_label, self.theme):
            if not value.strip():
                raise ValueError("public memory text fields cannot be empty")
        for evidence in self.public_evidence:
            evidence.validate()

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize only fields on the explicit public allowlist."""

        self.validate()
        return {
            "schemaVersion": self.schema_version,
            "memoryId": self.memory_id,
            "slug": self.slug,
            "occurredAt": _utc_iso(self.occurred_at),
            "publishedAt": _utc_iso(self.published_at),
            "kind": self.kind.value,
            "title": self.title,
            "summary": self.summary,
            "sourceLabel": self.source_label,
            "sourceType": self.source_type,
            "theme": self.theme,
            "editorialWeight": self.editorial_weight,
            "clusterId": self.cluster_id,
            "relatedProjects": list(self.related_projects),
            "relatedWriting": list(self.related_writing),
            "publicEvidence": [
                {"label": item.label, "href": item.href} for item in self.public_evidence
            ],
            "tags": list(self.tags),
            "publicationMode": self.publication_mode,
        }
