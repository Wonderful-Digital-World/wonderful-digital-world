from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapters import workspace_records
from .public_release import (
    ReleaseNotReady,
    create_candidate,
    release_delay_from_environment,
    release_latest_eligible,
)

PROJECTION_PATH = Path("public/projections/wdw")
ALLOWED_PATH = re.compile(
    r"^public/projections/wdw/(?:manifest\.v1\.json|releases/release-[a-f0-9]{20}/(?:world|systems)\.v1\.json)$"
)


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _repository_root(path: Path) -> Path:
    requested = path.expanduser().resolve(strict=True)
    actual = Path(_git(requested, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if requested != actual:
        raise ValueError(f"website repository must be its Git root: {actual}")
    return actual


def _changed_projection_paths(repo: Path) -> list[str]:
    output = _git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        str(PROJECTION_PATH),
    )
    paths: list[str] = []
    for line in output.splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if not ALLOWED_PATH.fullmatch(path):
            raise ValueError(f"refusing unexpected public projection path: {path}")
        paths.append(path)
    return sorted(set(paths))


def _append_operation(state_root: Path, event: dict[str, Any]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    with (state_root / "operations.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish a delayed WDW projection to its website repository."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--website-repo", type=Path, required=True)
    parser.add_argument(
        "--delay-hours",
        type=float,
        help="Test/dev override; production is fixed at 24.",
    )
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    if args.push and not args.commit:
        parser.error("--push requires --commit")

    started_at = datetime.now(UTC)
    repository = _repository_root(args.website_repo)
    state_root = args.state_root.expanduser().resolve(strict=False)
    publish_root = repository / PROJECTION_PATH
    event: dict[str, Any] = {"at": started_at.isoformat(), "status": "started"}
    try:
        if args.commit and _git(repository, "diff", "--cached", "--name-only"):
            raise ValueError(
                "refusing to publish while the website repository has staged changes"
            )
        delay = release_delay_from_environment(args.delay_hours)
        records = [
            {"kind": type(record).__name__, **record.to_dict()}
            for record in workspace_records(
                args.workspace.expanduser().resolve(strict=True)
            )
        ]
        generated_at = datetime.now(UTC)
        candidate = create_candidate(
            records, state_root=state_root, now=generated_at, delay=delay
        )
        generated_candidate_id = candidate["candidateId"]
        event["candidateId"] = generated_candidate_id
        try:
            manifest = release_latest_eligible(
                state_root=state_root,
                now=datetime.now(UTC),
                publish_root=publish_root,
            )
        except ReleaseNotReady:
            event["status"] = "not-ready"
            print(json.dumps(event, indent=2))
            return

        paths = _changed_projection_paths(repository)
        event.update(
            {
                "status": "published",
                "candidateId": manifest["candidateId"],
                "releaseId": manifest["releaseId"],
                "paths": paths,
            }
        )
        if generated_candidate_id != manifest["candidateId"]:
            event["generatedCandidateId"] = generated_candidate_id
        if args.commit and paths:
            _git(repository, "add", "--", *paths)
            staged = _git(repository, "diff", "--cached", "--name-only").splitlines()
            if not staged or any(not ALLOWED_PATH.fullmatch(path) for path in staged):
                raise ValueError("staged publication path allowlist mismatch")
            _git(
                repository,
                "commit",
                "-m",
                f"Publish WDW projection {manifest['releaseId']}",
                "--",
                *paths,
            )
            event["commit"] = _git(repository, "rev-parse", "HEAD")
            if args.push:
                _git(repository, "push")
                event["pushed"] = True
        print(json.dumps(event, indent=2))
    except Exception as error:
        event.update({"status": "failed", "error": str(error)})
        raise
    finally:
        _append_operation(state_root, event)


if __name__ == "__main__":
    main()
