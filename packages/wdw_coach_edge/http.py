"""Small default-deny HTTP boundary for Cloudflare Tunnel origin traffic."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Type

from .audit import AuditLog
from .auth import CredentialStore
from .service import CoachEdgeService, EdgeError


MAX_BODY_BYTES = 64 * 1024


def handler_class(service: CoachEdgeService, credentials: CredentialStore, audit: AuditLog) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "WDWCoachEdge/1"

        def do_POST(self) -> None:  # noqa: N802
            tool = self.path.removeprefix("/v1/tools/") if self.path.startswith("/v1/tools/") else "unroutable"
            trace_id = self.headers.get("X-WDW-Trace-Id", "rejected")[:128]
            principal = credentials.authenticate(self.headers.get("Authorization"))
            if principal is None:
                self._send(401, {"error": {"code": "unauthorized", "message": "valid bearer credential required"}})
                audit.write(trace_id=trace_id, tool=tool, outcome="rejected", http_status=401)
                return
            if not self.path.startswith("/v1/tools/"):
                self._send(404, {"error": {"code": "not_found", "message": "route is not exposed"}})
                audit.write(trace_id=trace_id, tool=tool, outcome="rejected", http_status=404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_BODY_BYTES:
                    raise EdgeError(413, "body_too_large", "request body exceeds limit")
                payload = json.loads(self.rfile.read(length))
                result = service.call(tool, payload, principal)
            except (ValueError, json.JSONDecodeError):
                result = None
                error = EdgeError(400, "invalid_json", "request body must be JSON")
            except EdgeError as exc:
                result = None
                error = exc
            if result is None:
                self._send(error.status, {"error": {"code": error.code, "message": str(error)}})
                audit.write(trace_id=trace_id, tool=tool, outcome="rejected", http_status=error.status)
                return
            self._send(result.status, result.body, trace_id=result.trace_id)
            audit.write(trace_id=result.trace_id, tool=tool, outcome="accepted", http_status=result.status)

        def do_GET(self) -> None:  # noqa: N802
            self._send(404, {"error": {"code": "not_found", "message": "route is not exposed"}})

        def _send(self, status: int, body: dict, *, trace_id: str | None = None) -> None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            if trace_id:
                self.send_header("X-WDW-Trace-Id", trace_id)
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def make_server(host: str, port: int, service: CoachEdgeService, credentials: CredentialStore, audit: AuditLog) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Coach edge must bind to loopback")
    return ThreadingHTTPServer((host, port), handler_class(service, credentials, audit))
