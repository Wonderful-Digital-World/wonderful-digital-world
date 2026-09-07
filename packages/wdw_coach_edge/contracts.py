"""Strict public contracts for the narrow resident edge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CONTRACT_VERSION = "1"


class ContractError(ValueError):
    pass


def exact_object(value: Any, fields: set[str], *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ContractError(f"{name} must contain exactly: {', '.join(sorted(fields))}")
    return value


def parse_status_request(value: Any) -> None:
    item = exact_object(value, {"contractVersion", "residentId"}, name="status request")
    if item["contractVersion"] != CONTRACT_VERSION or item["residentId"] != "coach":
        raise ContractError("unsupported status contract or resident")


@dataclass(frozen=True)
class TurnRequest:
    request_id: str
    conversation_id: str
    actor_id: str
    message: str
    local_date: str
    timezone: str


def parse_turn_request(value: Any) -> TurnRequest:
    item = exact_object(
        value,
        {"contractVersion", "residentId", "requestId", "conversationId", "actorId", "message", "localDate", "timezone"},
        name="turn request",
    )
    if item["contractVersion"] != CONTRACT_VERSION or item["residentId"] != "coach":
        raise ContractError("unsupported turn contract or resident")
    for field in ("requestId", "conversationId", "actorId", "message", "localDate", "timezone"):
        if not isinstance(item[field], str) or not item[field].strip():
            raise ContractError(f"{field} must be a non-empty string")
    if len(item["message"]) > 8_000:
        raise ContractError("message is too long")
    try:
        date.fromisoformat(item["localDate"])
    except ValueError as exc:
        raise ContractError("localDate must be an ISO date") from exc
    try:
        ZoneInfo(item["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ContractError("timezone must be an IANA timezone") from exc
    return TurnRequest(
        request_id=item["requestId"],
        conversation_id=item["conversationId"],
        actor_id=item["actorId"],
        message=item["message"],
        local_date=item["localDate"],
        timezone=item["timezone"],
    )
