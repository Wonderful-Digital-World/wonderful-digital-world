"""Transport translation without domain judgment."""

from typing import Protocol

from wdw_core import Artifact


class Connector(Protocol):
    name: str

    def translate(self, payload: bytes, *, external_id: str) -> Artifact:
        """Translate source bytes while preserving provenance."""
        ...
