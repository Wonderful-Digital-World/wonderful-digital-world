from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .adapters import DISPLAY_NAMES, RUNTIME_ACTIVITY_SCHEMA, RUNTIME_ACTIVITY_STATES
from .contracts import ResidentState


def activity_log_path(workspace: Path) -> Path:
    """Return the single runtime activity feed consumed by the command center."""
    configured = os.environ.get("WDW_RESIDENT_ACTIVITY_LOG")
    return Path(configured) if configured else workspace / ".wdw" / "resident-activity-v1.jsonl"


def append_resident_activity(
    path: Path,
    *,
    resident_id: str,
    state: str | ResidentState,
    summary: str,
    evidence_references: Iterable[str] = (),
    run_id: str | None = None,
    occurred_at: datetime | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    """Validate and append one canonical resident runtime event."""
    if resident_id not in DISPLAY_NAMES:
        raise ValueError(f"unknown residentId: {resident_id!r}")
    try:
        canonical_state = state if isinstance(state, ResidentState) else ResidentState(state)
    except ValueError as exc:
        raise ValueError(f"invalid canonical resident state: {state!r}") from exc
    if canonical_state not in RUNTIME_ACTIVITY_STATES:
        raise ValueError(f"resident state is not available at runtime: {canonical_state.value}")
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("summary must be non-empty")
    if run_id is not None and not run_id.strip():
        raise ValueError("run_id must be non-empty when present")
    references = list(evidence_references)
    if any(not isinstance(reference, str) or not reference.strip() for reference in references):
        raise ValueError("evidence references must be non-empty strings")
    timestamp = occurred_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("occurred_at must be timezone-aware")

    record: dict[str, object] = {
        "schema": RUNTIME_ACTIVITY_SCHEMA,
        "eventId": event_id or f"runtime-{uuid4()}",
        "residentId": resident_id,
        "state": canonical_state.value,
        "occurredAt": timestamp.isoformat(),
        "summary": clean_summary,
        "evidenceReferences": references,
    }
    if run_id is not None:
        record["runId"] = run_id.strip()

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a canonical WDW resident runtime event.")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--resident", required=True, choices=tuple(DISPLAY_NAMES))
    parser.add_argument(
        "--state", required=True,
        choices=tuple(sorted(state.value for state in RUNTIME_ACTIVITY_STATES)),
    )
    parser.add_argument("--summary", required=True)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--run-id")
    args = parser.parse_args()
    record = append_resident_activity(
        activity_log_path(args.workspace), resident_id=args.resident, state=args.state,
        summary=args.summary, evidence_references=args.evidence, run_id=args.run_id,
    )
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
