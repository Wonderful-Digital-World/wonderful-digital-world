from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


class EvidenceState(StrEnum):
    KNOWN = "known"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    STALE = "stale"
    INSUFFICIENT = "insufficient-evidence"


class ResidentState(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    NEEDS_ATTENTION = "needs-attention"
    UNAVAILABLE = "unavailable"


class AttentionState(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ReviewOutcome(StrEnum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not-relevant"
    DEFERRED = "deferred"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


@dataclass(frozen=True, slots=True)
class ObservabilityRecord:
    record_id: str
    occurred_at: datetime
    observed_at: datetime
    evidence_state: EvidenceState = EvidenceState.KNOWN

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id is required")
        _aware(self.occurred_at)
        _aware(self.observed_at)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["occurred_at"] = self.occurred_at.isoformat()
        result["observed_at"] = self.observed_at.isoformat()
        result["evidence_state"] = self.evidence_state.value
        return result


@dataclass(frozen=True, slots=True)
class ResidentSnapshot(ObservabilityRecord):
    resident_id: str = ""
    display_name: str = ""
    state: ResidentState = ResidentState.UNAVAILABLE
    status_summary: str = ""
    last_meaningful_activity_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        result = ObservabilityRecord.to_dict(self)
        result["state"] = self.state.value
        result["last_meaningful_activity_at"] = (
            self.last_meaningful_activity_at.isoformat()
            if self.last_meaningful_activity_at
            else None
        )
        return result


@dataclass(frozen=True, slots=True)
class MeaningfulActivity(ObservabilityRecord):
    resident_id: str = ""
    kind: str = ""
    summary: str = ""
    outcome: str = ""
    source_ref: str | None = None
    contract_version: str = "1.0"
    canonical_owner: str = ""
    actor: str = ""
    links: Mapping[str, Any] = field(default_factory=dict)
    evidence_links: tuple[str, ...] = ()
    compute_provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = ObservabilityRecord.to_dict(self)
        result["activity_kind"] = result.pop("kind")
        return result


@dataclass(frozen=True, slots=True)
class AttentionItem(ObservabilityRecord):
    resident_id: str = ""
    owner: str = ""
    status: AttentionState = AttentionState.OPEN
    reason: str = ""
    category: str = ""
    summary: str = ""
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    evidence_ref: str | None = None
    source_ref: str | None = None
    related_work_item_id: str | None = None
    deep_link: str | None = None
    contract_version: str = "1.0"

    def __post_init__(self) -> None:
        ObservabilityRecord.__post_init__(self)
        if self.updated_at is not None:
            _aware(self.updated_at)
        if self.resolved_at is not None:
            _aware(self.resolved_at)
        if self.status == AttentionState.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved attention requires resolved_at")

    def to_dict(self) -> dict[str, Any]:
        result = ObservabilityRecord.to_dict(self)
        result["status"] = self.status.value
        result["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        result["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
        return result


@dataclass(frozen=True, slots=True)
class Ingestion(ObservabilityRecord):
    resident_id: str = ""
    source_kind: str = ""
    item_count: int | None = None
    status: str = "unknown"
    contract_version: str = "1.0"
    canonical_owner: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source_details: Mapping[str, Any] = field(default_factory=dict)
    emitted_count: int | None = None
    loaded_count: int | None = None
    freshness: Mapping[str, Any] = field(default_factory=dict)
    processor: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = ObservabilityRecord.to_dict(self)
        result["started_at"] = self.started_at.isoformat() if self.started_at else None
        result["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return result


@dataclass(frozen=True, slots=True)
class ModelVersion(ObservabilityRecord):
    model_id: str = ""
    version: str = ""
    purpose: str = ""
    status: str = "unknown"


@dataclass(frozen=True, slots=True)
class EvaluationRun(ObservabilityRecord):
    model_id: str = ""
    model_version: str = ""
    thought_count: int | None = None
    candidate_count: int | None = None
    reviewed_count: int | None = None
    mean_similarity: float | None = None
    precision_at_k: float | Mapping[str, Any] | None = None
    median_similarity: float | None = None
    min_similarity: float | None = None
    max_similarity: float | None = None
    score_distribution: Mapping[str, Any] = field(default_factory=dict)
    rank_behavior: tuple[Mapping[str, Any], ...] | Mapping[str, Any] = field(default_factory=dict)
    reciprocal_graph: Mapping[str, Any] = field(default_factory=dict)
    analysis_version: str | None = None
    readiness: str | Mapping[str, Any] = "unknown"
    top_candidates: tuple[Mapping[str, Any], ...] = ()
    source_ref: str | None = None
    canonical_owner: str = "mini-me"
    read_only: bool = True
    contract_version: str = "1.0"
    availability_reason: str | None = None
    evaluation_name: str | None = None
    evaluation_version: str | None = None
    purpose: str | None = None
    dataset: Mapping[str, Any] = field(default_factory=dict)
    analysis_versions: tuple[str, ...] = ()
    models: tuple[Mapping[str, Any], ...] = ()
    evaluation_code_version: str | None = None
    reproducibility: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def precision_at_k_state(self) -> EvidenceState:
        if isinstance(self.precision_at_k, Mapping):
            states = {
                str(item.get("state"))
                for item in self.precision_at_k.values()
                if isinstance(item, Mapping)
            }
            return EvidenceState.KNOWN if "available" in states else EvidenceState.INSUFFICIENT
        if self.reviewed_count is None:
            return EvidenceState.UNKNOWN
        if self.reviewed_count == 0:
            return EvidenceState.INSUFFICIENT
        if self.precision_at_k is None:
            return EvidenceState.UNKNOWN
        return EvidenceState.KNOWN


@dataclass(frozen=True, slots=True)
class ReviewDecision(ObservabilityRecord):
    evaluation_id: str = ""
    candidate_id: str = ""
    reviewer: str = ""
    outcome: ReviewOutcome = ReviewOutcome.DEFERRED
    note: str | None = None
    contract_version: str = "1.0"
    canonical_owner: str = ""
    read_only: bool = False
    review_kind: str = ""
    subject_kind: str = ""
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = ObservabilityRecord.to_dict(self)
        result["outcome"] = self.outcome.value
        return result


@dataclass(frozen=True, slots=True)
class ComputeUsage(ObservabilityRecord):
    resident_id: str = ""
    provider: str = ""
    model: str = ""
    input_units: int = 0
    output_units: int = 0
    estimated_cost: float | None = None
    currency: str = "USD"
    provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MorningInsightOperation(ObservabilityRecord):
    occurrence_id: str = ""
    operation: str = "coach_morning_insight"
    status: str = "incomplete"
    stages: tuple[str, ...] = ()
    insight: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    personalization: Mapping[str, Any] = field(default_factory=dict)
    current_state: Mapping[str, Any] = field(default_factory=dict)
    recent_observations: Mapping[str, Any] = field(default_factory=dict)
    historical_context: Mapping[str, Any] = field(default_factory=dict)
    prediction: Mapping[str, Any] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    warnings: tuple[str, ...] = ()
    failure: Mapping[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None
    output_message_id: str | None = None
    delivery_id: str | None = None
    transport_message_id: str | None = None
    external_message_id: str | None = None
    delivery_status: str | None = None
    source_ref: str | None = None
    contract_version: str = "1.0"
    operational_owner: str = "agent-harness"
    canonical_owner: str = "human-model"
    read_only: bool = True


RECORD_TYPES = {
    cls.__name__: cls
    for cls in (
        ResidentSnapshot,
        MeaningfulActivity,
        AttentionItem,
        Ingestion,
        ModelVersion,
        EvaluationRun,
        ReviewDecision,
        ComputeUsage,
        MorningInsightOperation,
    )
}
