"""Fixed-origin client for the existing local Coach service."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CoachClientError(RuntimeError):
    pass


class CoachClient:
    def __init__(self, origin: str = "http://127.0.0.1:4350", timeout: float = 5.0) -> None:
        if origin != "http://127.0.0.1:4350":
            raise ValueError("Coach origin is fixed to its commissioned loopback address")
        self.origin = origin
        self.timeout = timeout

    def get_json(self, path: str) -> dict:
        if path not in {"/health", "/v1/runtime"}:
            raise ValueError("Coach client path is not allowlisted")
        return self._request("GET", path)

    def invoke(self, payload: dict) -> dict:
        return self._request("POST", "/v1/invocations", payload)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.origin + path,
            method=method,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise CoachClientError("Coach loopback service is unavailable or returned invalid data") from exc
        if not isinstance(value, dict):
            raise CoachClientError("Coach loopback service returned a non-object")
        return value
