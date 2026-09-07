"""Transport coordinator for the Coach edge; Coach retains domain interpretation."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Callable

from .auth import Principal
from .client import CoachClient, CoachClientError
from .contracts import ContractError, parse_status_request, parse_turn_request
from .fixture import FixtureEvidence
from .store import ReplayConflict, RequestInProgress, TurnStore


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
        fixture: FixtureEvidence | None = None,
        turn_store: TurnStore | None = None,
        enabled_tools: frozenset[str] = frozenset({"coach_get_status"}),
        trace_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.client = client
        self.coach_commit = coach_commit
        self.harness_commit = harness_commit
        self.identity_hash = identity_hash
        self.fixture = fixture
        self.turn_store = turn_store
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
        if tool == "coach_turn":
            return EdgeResult(200, self._turn(payload, trace_id, principal), trace_id)
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

    def _turn(self, payload: object, trace_id: str, principal: Principal) -> dict:
        if self.fixture is None or self.turn_store is None:
            raise EdgeError(404, "unknown_tool", "tool is not allowlisted")
        try:
            request = parse_turn_request(payload)
        except ContractError as exc:
            raise EdgeError(400, "invalid_request", str(exc)) from exc
        if request.actor_id not in principal.allowed_actors:
            raise EdgeError(403, "actor_forbidden", "actorId is not authorized for this credential")
        if (request.local_date, request.timezone) != (self.fixture.local_date, self.fixture.timezone):
            raise EdgeError(400, "fixture_scope_mismatch", "requested date and timezone must match the configured fixture")
        invocation = {
            "contractVersion": "1.0",
            "invocation": {"id": request.request_id, "participantId": "coach", "correlationId": request.conversation_id},
            "context": {
                "trigger": {"type": "message", "body": request.message},
                "recentHistory": [],
                "reality": {"humanModel": self.fixture.human_model},
                "actorId": request.actor_id,
                "participantId": request.actor_id,
                "localDate": request.local_date,
                "timezone": request.timezone,
                "evidenceContext": {
                    "sourceType": self.fixture.envelope["sourceType"],
                    "sourceReference": self.fixture.envelope["sourceReference"],
                    "observedAt": self.fixture.envelope["observedAt"],
                    "asOf": self.fixture.envelope["asOf"],
                    "freshness": self.fixture.envelope["freshness"],
                },
            },
        }
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            cached = self.turn_store.reserve(request.request_id, request_hash, trace_id, self.fixture.envelope, invocation)
        except ReplayConflict as exc:
            raise EdgeError(409, "replay_conflict", str(exc)) from exc
        except RequestInProgress as exc:
            raise EdgeError(409, "request_in_progress", str(exc)) from exc
        if cached is not None:
            return cached
        try:
            raw = self.client.invoke(invocation)
        except CoachClientError as exc:
            self.turn_store.fail(request.request_id)
            raise EdgeError(503, "coach_unavailable", str(exc)) from exc
        try:
            public, proposals = self._public_turn_response(raw, request)
            self.turn_store.complete(request.request_id, raw, public, proposals)
        except EdgeError:
            self.turn_store.fail(request.request_id)
            raise
        except Exception as exc:
            self.turn_store.fail(request.request_id)
            raise EdgeError(500, "turn_persistence_failed", "could not persist Coach response") from exc
        return public

    @staticmethod
    def _public_turn_response(raw: dict, request: object) -> tuple[dict, list[dict]]:
        if not isinstance(raw, dict) or raw.get("contractVersion") != "1.0" or raw.get("invocationId") != request.request_id:
            raise EdgeError(502, "invalid_coach_response", "Coach response identity is malformed")
        messages = raw.get("publicMessages")
        evidence = raw.get("evidenceReferences")
        uncertainties = raw.get("uncertainties")
        extensions = raw.get("extensions", {})
        proposed = extensions.get("wonderful.proposedActions", {}) if isinstance(extensions, dict) else {}
        proposals = proposed.get("actions", []) if isinstance(proposed, dict) else []
        if not isinstance(messages, list) or not all(isinstance(item, dict) and isinstance(item.get("body"), str) for item in messages):
            raise EdgeError(502, "invalid_coach_response", "Coach publicMessages are malformed")
        if (
            not isinstance(evidence, list)
            or not all(isinstance(item, str) for item in evidence)
            or not isinstance(uncertainties, list)
            or not all(isinstance(item, str) for item in uncertainties)
            or not isinstance(proposals, list)
        ):
            raise EdgeError(502, "invalid_coach_response", "Coach evidence, uncertainty, or proposal output is malformed")
        summaries = []
        for action in proposals:
            if not isinstance(action, dict) or action.get("confirmationRequired") is not True:
                raise EdgeError(502, "unsafe_coach_response", "all proposed actions must require confirmation")
            if not all(isinstance(action.get(field), str) for field in ("actionId", "actionType", "summary", "targetSystem")):
                raise EdgeError(502, "invalid_coach_response", "Coach proposal is malformed")
            summaries.append({field: action[field] for field in ("actionId", "actionType", "summary", "targetSystem", "confirmationRequired")})
        return ({
            "contractVersion": "1",
            "residentId": "coach",
            "requestId": request.request_id,
            "conversationId": request.conversation_id,
            "messages": [item["body"] for item in messages],
            "evidenceReferences": evidence,
            "uncertainties": uncertainties,
            "proposalSummaries": summaries,
        }, proposals)
