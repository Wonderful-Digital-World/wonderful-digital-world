"""Strict public contracts for the narrow resident edge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
