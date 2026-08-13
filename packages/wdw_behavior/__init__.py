"""Separation between evidence, interpretations, and proposed actions."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Interpretation:
    resident: str
    artifact_id: str
    summary: str
    confidence: float
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ProposedAction:
    resident: str
    capability: str
    rationale: str
    parameters: Mapping[str, Any]


def bounded_interpretation(
    *, resident: str, artifact_id: str, summary: str, confidence: float
) -> Interpretation:
    return Interpretation(resident, artifact_id, summary, confidence, {})
