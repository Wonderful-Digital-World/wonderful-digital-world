"""A small deterministic reference for one persistent-world iteration."""

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

State = TypeVar("State")
Evidence = TypeVar("Evidence")


@dataclass(frozen=True, slots=True)
class StepResult(Generic[State]):
    state: State
    acted: bool
    reason: str


def reconcile_once(
    state: State,
    evidence: Evidence,
    *,
    understand: Callable[[State, Evidence], object],
    reconcile: Callable[[State, object], StepResult[State]],
) -> StepResult[State]:
    """Observe -> understand -> reconcile; effect execution stays explicit."""
    interpretation = understand(state, evidence)
    return reconcile(state, interpretation)
