"""Transport coordinator for the Coach edge; Coach retains domain interpretation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from .auth import Principal
from .client import CoachClient, CoachClientError
from .contracts import ContractError, parse_status_request


class EdgeError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class EdgeResult:
    status: int
    body: dict
    trace_id: str


class CoachEdgeService:
    def __init__(
        self,
        client: CoachClient,
        *,
        coach_commit: str,
        harness_commit: str,
        identity_hash: str,
        enabled_tools: frozenset[str] = frozenset({"coach_get_status"}),
        trace_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.client = client
        self.coach_commit = coach_commit
        self.harness_commit = harness_commit
        self.identity_hash = identity_hash
        self.enabled_tools = enabled_tools
        self.trace_factory = trace_factory

    def call(self, tool: str, payload: object, principal: Principal) -> EdgeResult:
        trace_id = self.trace_factory()
        if principal.resident_id != "coach":
            raise EdgeError(403, "forbidden", "credential is not valid for Coach")
        if tool not in self.enabled_tools:
            raise EdgeError(404, "unknown_tool", "tool is not allowlisted")
        if tool == "coach_get_status":
            return EdgeResult(200, self._status(payload), trace_id)
        raise EdgeError(404, "unknown_tool", "tool is not allowlisted")

    def _status(self, payload: object) -> dict:
        try:
            parse_status_request(payload)
            health = self.client.get_json("/health")
            runtime = self.client.get_json("/v1/runtime")
        except ContractError as exc:
            raise EdgeError(400, "invalid_request", str(exc)) from exc
        except CoachClientError as exc:
            raise EdgeError(503, "coach_unavailable", str(exc)) from exc
        healthy = health.get("status") == "ok" and runtime.get("participantId") == "coach"
        return {
            "contractVersion": "1",
            "residentId": "coach",
            "identityHash": self.identity_hash,
            "coachCommit": self.coach_commit,
            "harnessCommit": self.harness_commit,
            "status": "ready" if healthy else "degraded",
            "dependencies": {
                "coach": "available" if healthy else "unavailable",
                "humanModel": "not_checked",
            },
        }
