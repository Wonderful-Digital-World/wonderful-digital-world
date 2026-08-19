from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .adapters import workspace_records
from .public_release import (
    ReleaseNotReady,
    create_candidate,
    release_delay_from_environment,
    release_latest_eligible,
)
from .sample import synthetic_records
from .store import OperatorStore


def _event_time(row: dict[str, object]) -> datetime:
    parsed = datetime.fromisoformat(str(row["occurred_at"]))
    if parsed.tzinfo is None:
        raise ValueError("event timestamps must be timezone-aware")
    return parsed


def releasable_records(
    records: list[dict[str, object]], *, now: datetime, delay: timedelta
) -> tuple[list[dict[str, object]], datetime]:
    """Retain the legacy per-record delay helper for API compatibility."""
    cutoff = now - delay
    eligible = [row for row in records if _event_time(row) <= cutoff]
    source_time = max((_event_time(row) for row in eligible), default=cutoff)
    return eligible, source_time


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and publish delayed, allowlisted WDW public projections."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument(
        "--workspace", type=Path, help="Read real projections from the WDW workspace."
    )
    source.add_argument(
        "--sample", action="store_true", help="Use explicitly synthetic fixtures."
    )
    parser.add_argument(
        "--delay-hours",
        type=float,
        help="Test/dev override; production is fixed at 24.",
    )
    parser.add_argument(
        "--state-root", type=Path, default=Path(".wdw/public-projection")
    )
    parser.add_argument(
        "--publish-root", type=Path, help="Website's public/projections/wdw directory."
    )
    parser.add_argument("--candidate-only", action="store_true")
    args = parser.parse_args()
    now = datetime.now(UTC)
    delay = release_delay_from_environment(args.delay_hours)
    if args.sample:
        records = [
            {"kind": type(record).__name__, **record.to_dict()}
            for record in synthetic_records(now - delay - timedelta(hours=1))
        ]
    elif args.workspace:
        records = [
            {"kind": type(record).__name__, **record.to_dict()}
            for record in workspace_records(args.workspace)
        ]
    elif args.database:
        records = OperatorStore(args.database).records(limit=1000)
    candidate = create_candidate(
        records, state_root=args.state_root, now=now, delay=delay
    )
    result: dict[str, object] = {"candidate": candidate, "release": None}
    if not args.candidate_only:
        try:
            result["release"] = release_latest_eligible(
                state_root=args.state_root, now=now, publish_root=args.publish_root
            )
        except ReleaseNotReady as error:
            print(str(error), file=sys.stderr)
    print(json.dumps(result, indent=2), end="\n")


if __name__ == "__main__":
    main()
