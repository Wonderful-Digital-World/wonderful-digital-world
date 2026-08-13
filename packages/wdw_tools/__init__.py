"""Explicit authority checks for effects."""

from dataclasses import dataclass, field


class AuthorityDenied(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class Authority:
    subject: str
    capabilities: frozenset[str] = field(default_factory=frozenset)

    def require(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise AuthorityDenied(
                f"{self.subject!r} lacks capability {capability!r}"
            )
