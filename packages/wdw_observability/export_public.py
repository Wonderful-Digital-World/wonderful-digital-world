from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adapters import workspace_records
from .projections import private_overview, public_systems_projection
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
    cutoff = now - delay
    eligible = [row for row in records if _event_time(row) <= cutoff]
    source_time = max((_event_time(row) for row in eligible), default=cutoff)
    return eligible, source_time


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the delayed, allowlisted public Systems projection.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument("--workspace", type=Path, help="Read real projections from the WDW workspace.")
    source.add_argument("--sample", action="store_true", help="Use explicitly synthetic fixtures.")
    parser.add_argument("--delay-hours", type=float, default=24)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    delay = timedelta(hours=args.delay_hours)
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
    records, source_time = releasable_records(records, now=now, delay=delay)
    private = private_overview(records, source_time)
    public = public_systems_projection(private, now=now, delay=delay)
    payload = json.dumps(public, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
