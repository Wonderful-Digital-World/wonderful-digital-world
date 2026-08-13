"""Run one synthetic ingress-to-projection slice of the persistent-world loop."""

from dataclasses import dataclass
from datetime import datetime, timezone

from wdw_core import Artifact
from wdw_harness import StepResult, reconcile_once
from wdw_inbox import Inbox
from wdw_interfaces import Projection


@dataclass(frozen=True)
class DemoState:
    revision: int = 0
    attention: tuple[str, ...] = ()


def understand(state: DemoState, artifact: Artifact) -> str:
    del state
    return artifact.body.decode("utf-8")


def reconcile(state: DemoState, interpretation: object) -> StepResult[DemoState]:
    summary = str(interpretation)
    next_state = DemoState(state.revision + 1, state.attention + (summary,))
    return StepResult(next_state, acted=False, reason="projection update only")


inbox = Inbox()
artifact = Artifact(
    artifact_id="artifact-demo-1",
    media_type="text/plain",
    body=b"A decision needs human judgment",
    source="synthetic-example",
    external_id="event-1",
)
receipt = inbox.receive(artifact)
result = reconcile_once(
    DemoState(), receipt.artifact, understand=understand, reconcile=reconcile
)
projection = Projection(
    contract_version="1.0",
    projection_id="projection-demo-1",
    generated_at=datetime.now(timezone.utc),
    source_revision=f"demo-{result.state.revision}",
    freshness_seconds=60,
    place="attention-room",
    payload={"attention": list(result.state.attention)},
    authorized_for=frozenset({"human"}),
)

print(projection.for_viewer("human").payload)
