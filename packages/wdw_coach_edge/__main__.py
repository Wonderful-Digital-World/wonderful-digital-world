from __future__ import annotations

import argparse
import os
from pathlib import Path

from .audit import AuditLog
from .auth import CredentialStore
from .client import CoachClient
from .http import make_server
from .fixture import load_fixture
from .service import CoachEdgeService
from .store import TurnStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the loopback-only WDW Coach edge")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument("--port", type=int, default=4380)
    parser.add_argument("--enable-sandbox-turn", action="store_true")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--request-store", type=Path)
    args = parser.parse_args()
    required = ("WDW_COACH_EXPECTED_COMMIT", "WDW_HARNESS_COMMIT", "WDW_COACH_IDENTITY_HASH")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        parser.error("missing environment: " + ", ".join(missing))
    audit = AuditLog(args.audit_log)
    fixture = None
    turn_store = None
    enabled_tools = {"coach_get_status"}
    if args.enable_sandbox_turn:
        if args.fixture is None or args.request_store is None:
            parser.error("--enable-sandbox-turn requires --fixture and --request-store")
        fixture = load_fixture(args.fixture)
        turn_store = TurnStore(args.request_store)
        enabled_tools.add("coach_turn")
    service = CoachEdgeService(
        CoachClient(),
        coach_commit=os.environ[required[0]],
        harness_commit=os.environ[required[1]],
        identity_hash=os.environ[required[2]],
        fixture=fixture,
        turn_store=turn_store,
        enabled_tools=frozenset(enabled_tools),
    )
    server = make_server("127.0.0.1", args.port, service, CredentialStore(args.credentials), audit)
    try:
        server.serve_forever()
    finally:
        audit.close()
        if turn_store is not None:
            turn_store.close()


if __name__ == "__main__":
    main()
