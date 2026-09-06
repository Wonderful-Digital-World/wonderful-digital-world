"""Independent resident credential validation for the Coach edge."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    resident_id: str
    allowed_actors: frozenset[str]


class CredentialStore:
    """Reload a small credential file on every request so revocation is immediate."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def authenticate(self, authorization: str | None) -> Principal | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        token = authorization.removeprefix("Bearer ")
        if not token:
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for item in raw.get("credentials", []):
            expected = item.get("tokenSha256")
            if (
                isinstance(expected, str)
                and hmac.compare_digest(digest, expected)
                and item.get("residentId") == "coach"
                and item.get("revoked") is False
            ):
                actors = item.get("allowedActorIds", [])
                if not isinstance(actors, list) or not all(isinstance(v, str) for v in actors):
                    return None
                return Principal("coach", frozenset(actors))
        return None
