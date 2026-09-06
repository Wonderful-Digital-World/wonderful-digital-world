from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from wdw_coach_edge.audit import AuditLog
from wdw_coach_edge.auth import CredentialStore
from wdw_coach_edge.http import make_server
from wdw_coach_edge.service import CoachEdgeService


class FakeCoach:
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    def get_json(self, path: str) -> dict:
        self.calls.append(path)
        return {"status": "ok"} if path == "/health" else {"participantId": "coach", "gitCommit": "misleading-head"}


@pytest.fixture
def edge(tmp_path: Path):
    token = "test-coach-secret"
    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"credentials": [{
        "residentId": "coach", "tokenSha256": hashlib.sha256(token.encode()).hexdigest(),
        "allowedActorIds": ["haley"], "revoked": False,
    }]}))
    audit = AuditLog(tmp_path / "audit.jsonl", max_bytes=500, backups=1)
    coach = FakeCoach()
    service = CoachEdgeService(
        coach, coach_commit="a0bc678", harness_commit="harness-pin", identity_hash="identity-hash",
        trace_factory=lambda: "trace-1",
    )
    server = make_server("127.0.0.1", 0, service, CredentialStore(credentials), audit)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], token, credentials, audit, coach, tmp_path
    server.shutdown()
    server.server_close()
    audit.close()


def post(edge, path: str, body: dict, token: str | None = None):
    port = edge[0]
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(request) as response:
            return response.status, json.load(response), dict(response.headers)
    except HTTPError as exc:
        return exc.code, json.load(exc), dict(exc.headers)


def test_status_is_authenticated_limited_and_idempotent(edge):
    request = {"contractVersion": "1", "residentId": "coach"}
    first = post(edge, "/v1/tools/coach_get_status", request, edge[1])
    second = post(edge, "/v1/tools/coach_get_status", request, edge[1])
    assert first[0] == second[0] == 200
    assert first[1] == second[1]
    assert first[1] == {
        "contractVersion": "1", "residentId": "coach", "identityHash": "identity-hash",
        "coachCommit": "a0bc678", "harnessCommit": "harness-pin", "status": "ready",
        "dependencies": {"coach": "available", "humanModel": "not_checked"},
    }
    assert "misleading-head" not in json.dumps(first[1])


def test_auth_revocation_unknown_tools_and_routes_are_default_denied(edge):
    request = {"contractVersion": "1", "residentId": "coach"}
    assert post(edge, "/v1/tools/coach_get_status", request)[0] == 401
    assert post(edge, "/v1/tools/coach_turn", request, edge[1])[0] == 404
    assert post(edge, "/v1/tools/read_file", request, edge[1])[0] == 404
    assert post(edge, "/v1/invocations", request, edge[1])[0] == 404
    raw = json.loads(edge[2].read_text())
    raw["credentials"][0]["revoked"] = True
    edge[2].write_text(json.dumps(raw))
    assert post(edge, "/v1/tools/coach_get_status", request, edge[1])[0] == 401


def test_logs_are_redacted_and_bounded(edge):
    request = {"contractVersion": "1", "residentId": "coach", "secret": "never-log-this"}
    for _ in range(20):
        post(edge, "/v1/tools/coach_get_status", request, edge[1])
    for path in edge[5].glob("audit.jsonl*"):
        assert path.stat().st_size <= 500
        content = path.read_text()
        assert "never-log-this" not in content
        for line in content.splitlines():
            assert set(json.loads(line)) == {"timestamp", "traceId", "tool", "outcome", "httpStatus"}


def test_non_loopback_bind_is_rejected(edge):
    with pytest.raises(ValueError, match="loopback"):
        make_server("0.0.0.0", 0, object(), object(), object())
