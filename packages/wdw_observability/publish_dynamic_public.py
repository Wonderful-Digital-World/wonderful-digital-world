from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import workspace_records
from .projections import private_overview, public_snapshot
from .sample import synthetic_records
from .store import OperatorStore


def upload_snapshot(
    endpoint: str,
    token: str,
    snapshot: dict[str, Any],
    *,
    attempts: int = 4,
) -> dict[str, Any]:
    """Upload one immutable envelope; retries are safe because its ID is content-addressed."""
    body = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "wdw-public-producer/1",
        },
        method="POST",
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == attempts - 1:
                raise
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
        time.sleep(min(2**attempt, 8))
    raise RuntimeError("snapshot upload exhausted retries")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sanitize current WDW state and upload an immutable delayed snapshot."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument("--workspace", type=Path)
    source.add_argument("--sample", action="store_true")
    parser.add_argument("--endpoint", default=os.getenv("WDW_PUBLIC_INGEST_URL"))
    parser.add_argument("--token", default=os.getenv("WDW_PUBLIC_INGEST_TOKEN"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    if args.sample:
        records = [
            {"kind": type(record).__name__, **record.to_dict()}
            for record in synthetic_records(now)
        ]
    elif args.workspace:
        records = [
            {"kind": type(record).__name__, **record.to_dict()}
            for record in workspace_records(args.workspace)
        ]
    else:
        records = OperatorStore(args.database).records(limit=1000)

    envelope = public_snapshot(
        private_overview(records, now),
        generated_at=now,
    )
    if args.dry_run:
        print(json.dumps(envelope, indent=2))
        return
    if not args.endpoint or not args.token:
        parser.error("--endpoint and --token (or matching environment variables) are required")
    result = upload_snapshot(args.endpoint, args.token, envelope)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
