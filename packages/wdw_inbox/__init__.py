"""Reference durable-ingress behavior using an in-memory adapter."""

from dataclasses import dataclass

from wdw_core import Artifact, WorkItem


@dataclass(frozen=True, slots=True)
class Receipt:
    artifact: Artifact
    created: bool


class Inbox:
    """Persist before acknowledgement and deduplicate transport retries."""

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._external_ids: dict[tuple[str, str], str] = {}
        self._work: dict[str, WorkItem] = {}

    def receive(self, artifact: Artifact) -> Receipt:
        key = (artifact.source, artifact.external_id)
        if existing_id := self._external_ids.get(key):
            return Receipt(self._artifacts[existing_id], created=False)
        if artifact.artifact_id in self._artifacts:
            raise ValueError("artifact_id already belongs to another receipt")
        self._artifacts[artifact.artifact_id] = artifact
        self._external_ids[key] = artifact.artifact_id
        return Receipt(artifact, created=True)

    def route(self, artifact_id: str, *, recipient: str, kind: str) -> WorkItem:
        if artifact_id not in self._artifacts:
            raise KeyError("persist the artifact before routing it")
        item = WorkItem(kind=kind, recipient=recipient, artifact_id=artifact_id)
        self._work[item.work_id] = item
        return item

    def artifact(self, artifact_id: str) -> Artifact:
        return self._artifacts[artifact_id]
