"""Load the single, safe Human Model fixture exposed by the sandbox turn."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractError, exact_object


@dataclass(frozen=True)
class FixtureEvidence:
    envelope: dict[str, Any]
    human_model: dict[str, Any]
    local_date: str
    timezone: str


def load_fixture(path: Path) -> FixtureEvidence:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("fixture is unreadable or malformed") from exc
    item = exact_object(
        value,
        {"fixtureVersion", "sourceType", "sourceReference", "observedAt", "asOf", "freshness", "scope", "humanModel"},
        name="fixture",
    )
    if item["fixtureVersion"] != "1" or item["sourceType"] != "human_model_daily_fitness_snapshot":
        raise ContractError("unsupported fixture")
    for field in ("sourceReference", "observedAt", "asOf"):
        if not isinstance(item[field], str) or not item[field]:
            raise ContractError(f"fixture {field} must be a non-empty string")
    freshness = exact_object(item["freshness"], {"state"}, name="fixture freshness")
    if freshness["state"] not in {"current", "stale", "missing"}:
        raise ContractError("fixture freshness state is unsupported")
    scope = exact_object(item["scope"], {"localDate", "timezone"}, name="fixture scope")
    if not all(isinstance(scope[field], str) and scope[field] for field in scope):
        raise ContractError("fixture scope values must be non-empty strings")
    human_model = item["humanModel"]
    if not isinstance(human_model, dict):
        raise ContractError("fixture humanModel must be an object")
    if freshness["state"] == "missing":
        if human_model != {"provenance": {"evidenceState": "unavailable"}}:
            raise ContractError("missing fixture must contain only unavailable provenance")
    else:
        hm = exact_object(human_model, {"provenance", "content"}, name="fixture humanModel")
        provenance = exact_object(hm["provenance"], {"evidenceState"}, name="fixture provenance")
        if provenance["evidenceState"] != "available" or not isinstance(hm["content"], dict):
            raise ContractError("available fixture must contain Human Model content")
        content_scope = hm["content"].get("scope")
        if not isinstance(content_scope, dict) or content_scope.get("localDate") != scope["localDate"] or content_scope.get("timezone") != scope["timezone"]:
            raise ContractError("fixture and Human Model scopes do not match")
    return FixtureEvidence(value, human_model, scope["localDate"], scope["timezone"])
