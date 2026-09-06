from __future__ import annotations

import argparse
import os
from pathlib import Path

from .audit import AuditLog
from .auth import CredentialStore
from .client import CoachClient
from .http import make_server
from .service import CoachEdgeService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the loopback-only WDW Coach edge")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument("--port", type=int, default=4380)
    args = parser.parse_args()
    required = ("WDW_COACH_EXPECTED_COMMIT", "WDW_HARNESS_COMMIT", "WDW_COACH_IDENTITY_HASH")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        parser.error("missing environment: " + ", ".join(missing))
    audit = AuditLog(args.audit_log)
    service = CoachEdgeService(
        CoachClient(),
        coach_commit=os.environ[required[0]],
        harness_commit=os.environ[required[1]],
        identity_hash=os.environ[required[2]],
    )
    server = make_server("127.0.0.1", args.port, service, CredentialStore(args.credentials), audit)
    try:
        server.serve_forever()
    finally:
        audit.close()


if __name__ == "__main__":
    main()
