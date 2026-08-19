from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PRODUCTION_DELAY = timedelta(hours=24)
WORLD_SCHEMA = "wdw.world.v1"
SYSTEMS_SCHEMA = "wdw.systems.v1"
MANIFEST_SCHEMA = "wdw.public-release-manifest.v1"
ALLOWED_STATUSES = frozenset(
    {"idle", "active", "waiting", "needs-attention", "unavailable"}
)
RESIDENTS = {
    "bridget": ("Bridget", "Orchestrator", "workshop"),
    "coach": ("Coach", "Coaching resident", "workshop"),
    "mini-me": ("Mini Me", "Research resident", "lab"),
    "banjo": ("Banjo", "Engineering resident", "workshop"),
}
PLACES = (
    {
        "placeId": "workshop",
        "name": "Workshop",
        "kind": "workshop",
        "status": "open",
        "href": "/world/#workshop",
    },
    {
        "placeId": "lab",
        "name": "Lab",
        "kind": "lab",
        "status": "open",
        "href": "/world/#lab",
    },
)


class ReleaseNotReady(RuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _utc(parsed)


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_integrity(value: Mapping[str, Any]) -> bool:
    digest = value.get("sha256")
    size = value.get("bytes")
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return isinstance(size, int) and not isinstance(size, bool) and size >= 0


def _non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nullable_finite_number(value: Any) -> bool:
    return value is None or (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _valid_identifier(value: Any, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(rf"{re.escape(prefix)}[a-f0-9]{{20}}", value) is not None
    )


def _validate_release_delay(value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("invalid public release delay")
    hours = float(value)
    environment = os.environ.get("WDW_ENV", "production").lower()
    if environment not in {"test", "dev", "development"} and hours != 24:
        raise ValueError("the production public release delay is fixed at 24 hours")
    return hours


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError(f"refusing symlinked publication directory: {path.parent}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"immutable candidate collision: {path}")
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable candidate collision: {path}")
        return
    _atomic_write(path, payload)


def release_delay_from_environment(requested_hours: float | None = None) -> timedelta:
    hours = 24 if requested_hours is None else requested_hours
    return timedelta(hours=_validate_release_delay(hours))


def build_artifacts(
    records: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime,
    delay: timedelta = PRODUCTION_DELAY,
) -> dict[str, dict[str, Any]]:
    rows = list(records)
    snapshots: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if row.get("kind") != "ResidentSnapshot":
            continue
        resident_id = str(row.get("resident_id", ""))
        if resident_id not in RESIDENTS or row.get("evidence_state") not in {
            "known",
            "stale",
        }:
            continue
        previous = snapshots.get(resident_id)
        if previous is None or _parse(str(row.get("observed_at", ""))) > _parse(
            str(previous.get("observed_at", ""))
        ):
            snapshots[resident_id] = row

    residents: list[dict[str, str]] = []
    for resident_id, (name, role, place_id) in RESIDENTS.items():
        snapshot = snapshots.get(resident_id)
        if snapshot is None:
            continue
        raw_status = str(snapshot.get("state", "unavailable"))
        status = (
            raw_status
            if snapshot.get("evidence_state") == "known"
            and raw_status in ALLOWED_STATUSES
            else "unavailable"
        )
        residents.append(
            {
                "residentId": resident_id,
                "name": name,
                "role": role,
                "placeId": place_id,
                "status": status,
            }
        )

    if "bridget" not in snapshots:
        raise ValueError("canonical Bridget state unavailable")

    attention_count = sum(row["status"] == "needs-attention" for row in residents)
    evaluations = [row for row in rows if row.get("kind") == "EvaluationRun"]
    latest_evaluation = max(
        evaluations,
        key=lambda row: _parse(str(row.get("observed_at", ""))),
        default={},
    )
    reviewed_raw = latest_evaluation.get("reviewed_count")
    reviewed = int(reviewed_raw) if reviewed_raw is not None else None
    precision_raw = latest_evaluation.get("precision_at_k")
    precision = (
        precision_raw
        if _nullable_finite_number(precision_raw)
        and precision_raw is not None
        and reviewed not in (None, 0)
        else None
    )
    precision_state = (
        "unknown"
        if reviewed is None
        else (
            "insufficient-evidence"
            if reviewed == 0
            else ("available" if precision is not None else "unknown")
        )
    )
    source_times = [
        _parse(str(row["observed_at"])) for row in rows if row.get("observed_at")
    ]
    source_observed_at = max(source_times, default=_utc(generated_at))
    state = (
        "known"
        if any(row.get("evidence_state") == "known" for row in snapshots.values())
        else "unknown"
    )
    world = {
        "schema": WORLD_SCHEMA,
        "schemaVersion": "1.0.0",
        "projectionId": "wdw-resident-public",
        "generatedAt": _stamp(generated_at),
        "status": "current" if state == "known" else "partial",
        "places": list(PLACES),
        "residents": residents,
        "activities": [],
        "attention": [],
    }
    systems = {
        "schema": SYSTEMS_SCHEMA,
        "generatedAt": _stamp(generated_at),
        "sourceObservedAt": _stamp(source_observed_at),
        "releaseDelayHours": delay.total_seconds() / 3600,
        "state": state,
        "residents": {
            "total": len(residents),
            "active": sum(row["status"] == "active" for row in residents),
            "needsAttention": attention_count,
        },
        "intelligence": {
            "thoughts": latest_evaluation.get("thought_count"),
            "candidates": latest_evaluation.get("candidate_count"),
            "reviewed": reviewed,
            "meanSimilarity": latest_evaluation.get("mean_similarity"),
            "precisionAtK": precision,
            "precisionAtKState": precision_state,
        },
    }
    validate_world(world)
    validate_systems(systems)
    return {"world.v1.json": world, "systems.v1.json": systems}


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"invalid {label} fields: {sorted(set(value) ^ expected)}")


def validate_world(value: Mapping[str, Any]) -> None:
    _exact_keys(
        value,
        {
            "schema",
            "schemaVersion",
            "projectionId",
            "generatedAt",
            "status",
            "places",
            "residents",
            "activities",
            "attention",
        },
        "World",
    )
    if value["schema"] != WORLD_SCHEMA or value["schemaVersion"] != "1.0.0":
        raise ValueError("unsupported World public schema")
    _parse(str(value["generatedAt"]))
    if value["projectionId"] != "wdw-resident-public" or value["status"] not in {
        "current",
        "partial",
    }:
        raise ValueError("invalid World public projection metadata")
    if not isinstance(value["places"], list) or not isinstance(
        value["residents"], list
    ):
        raise TypeError("invalid World public projection collections")
    if not isinstance(value["activities"], list) or not isinstance(
        value["attention"], list
    ):
        raise TypeError("invalid World public projection collections")
    for place in value["places"]:
        if not isinstance(place, Mapping):
            raise TypeError("invalid public place")
        _exact_keys(place, {"placeId", "name", "kind", "status", "href"}, "place")
        if not all(isinstance(field, str) for field in place.values()):
            raise ValueError("invalid public place values")
    place_ids = [place["placeId"] for place in value["places"]]
    if len(place_ids) != len(set(place_ids)) or value["places"] != list(PLACES):
        raise ValueError("invalid public place identities")
    for resident in value["residents"]:
        if not isinstance(resident, Mapping):
            raise TypeError("invalid public resident")
        _exact_keys(
            resident, {"residentId", "name", "role", "placeId", "status"}, "resident"
        )
        if (
            not all(isinstance(field, str) for field in resident.values())
            or resident["status"] not in ALLOWED_STATUSES
        ):
            raise ValueError("invalid public resident status")
        if resident["residentId"] not in RESIDENTS or resident["placeId"] not in {
            place["placeId"] for place in PLACES
        }:
            raise ValueError("invalid public resident identity")
        name, role, place_id = RESIDENTS[resident["residentId"]]
        if (resident["name"], resident["role"], resident["placeId"]) != (
            name,
            role,
            place_id,
        ):
            raise ValueError("invalid public resident identity fields")
    resident_ids = [resident["residentId"] for resident in value["residents"]]
    if len(resident_ids) != len(set(resident_ids)):
        raise ValueError("duplicate public resident identity")
    if value["activities"] or value["attention"]:
        raise ValueError(
            "resident public projection does not publish activity or attention details"
        )


def validate_systems(value: Mapping[str, Any]) -> None:
    _exact_keys(
        value,
        {
            "schema",
            "generatedAt",
            "sourceObservedAt",
            "releaseDelayHours",
            "state",
            "residents",
            "intelligence",
        },
        "Systems",
    )
    delay = value["releaseDelayHours"]
    if value["schema"] != SYSTEMS_SCHEMA:
        raise ValueError("unsupported Systems public schema or delay")
    _validate_release_delay(delay)
    generated = _parse(str(value["generatedAt"]))
    observed = _parse(str(value["sourceObservedAt"]))
    if observed > generated or value["state"] not in {"known", "unknown"}:
        raise ValueError("invalid Systems public projection metadata")
    if not isinstance(value["residents"], Mapping) or not isinstance(
        value["intelligence"], Mapping
    ):
        raise TypeError("invalid Systems public aggregates")
    _exact_keys(
        value["residents"], {"total", "active", "needsAttention"}, "resident aggregate"
    )
    _exact_keys(
        value["intelligence"],
        {
            "thoughts",
            "candidates",
            "reviewed",
            "meanSimilarity",
            "precisionAtK",
            "precisionAtKState",
        },
        "intelligence aggregate",
    )
    if not all(_non_negative_integer(metric) for metric in value["residents"].values()):
        raise ValueError("invalid resident aggregate")
    if (
        value["residents"]["active"] > value["residents"]["total"]
        or value["residents"]["needsAttention"] > value["residents"]["total"]
    ):
        raise ValueError("inconsistent resident aggregate")
    intelligence = value["intelligence"]
    for key in ("thoughts", "candidates", "reviewed"):
        if intelligence[key] is not None and not _non_negative_integer(
            intelligence[key]
        ):
            raise ValueError("invalid intelligence count")
    for key in ("meanSimilarity", "precisionAtK"):
        if not _nullable_finite_number(intelligence[key]):
            raise ValueError("invalid intelligence metric")
    if intelligence["precisionAtKState"] not in {
        "available",
        "insufficient-evidence",
        "unknown",
    }:
        raise ValueError("invalid intelligence evidence state")


def create_candidate(
    records: Iterable[Mapping[str, Any]],
    *,
    state_root: Path,
    now: datetime,
    delay: timedelta,
) -> dict[str, Any]:
    state_root = state_root.expanduser()
    if state_root.is_symlink():
        raise ValueError(f"refusing symlinked state root: {state_root}")
    generated = _utc(now)
    _validate_release_delay(delay.total_seconds() / 3600)
    artifacts = build_artifacts(records, generated_at=generated, delay=delay)
    artifact_payloads = {name: _json_bytes(value) for name, value in artifacts.items()}
    source_observed = artifacts["systems.v1.json"]["sourceObservedAt"]
    candidate_id = _candidate_identifier(artifact_payloads, _stamp(generated))
    candidate = {
        "schema": "wdw.public-candidate.v1",
        "candidateId": candidate_id,
        "generatedAt": _stamp(generated),
        "sourceObservedAt": source_observed,
        "eligibleAt": _stamp(generated + delay),
        "releaseDelayHours": delay.total_seconds() / 3600,
        "artifacts": {
            name: {"sha256": _sha(payload), "bytes": len(payload)}
            for name, payload in artifact_payloads.items()
        },
    }
    _validate_candidate(candidate)
    candidates_root = state_root / "candidates"
    if candidates_root.is_symlink():
        raise ValueError(f"refusing symlinked candidate root: {candidates_root}")
    directory = candidates_root / candidate_id
    if directory.is_symlink():
        raise ValueError(f"refusing symlinked candidate directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    for name, payload in artifact_payloads.items():
        _write_immutable(directory / name, payload)
    _write_immutable(directory / "candidate.json", _json_bytes(candidate))
    return candidate


def _candidate_identifier(payloads: Mapping[str, bytes], generated_at: str) -> str:
    identity = b"".join(
        payloads[name] for name in sorted(payloads)
    ) + generated_at.encode("utf-8")
    return f"candidate-{_sha(identity)[:20]}"


def _eligible_candidates(
    state_root: Path, now: datetime
) -> list[tuple[datetime, Path, dict[str, Any]]]:
    result = []
    for path in (state_root / "candidates").glob("candidate-*/candidate.json"):
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError(f"refusing symlinked candidate path: {path}")
        candidate = json.loads(path.read_text(encoding="utf-8"))
        _validate_candidate(candidate)
        if path.parent.name != candidate["candidateId"]:
            raise ValueError(
                f"candidate directory does not match candidateId: {path.parent}"
            )
        eligible = _parse(candidate["eligibleAt"])
        if eligible <= _utc(now):
            result.append((eligible, path.parent, candidate))
    return sorted(result, key=lambda item: item[0], reverse=True)


def _validate_candidate(candidate: Mapping[str, Any]) -> None:
    _exact_keys(
        candidate,
        {
            "schema",
            "candidateId",
            "generatedAt",
            "sourceObservedAt",
            "eligibleAt",
            "releaseDelayHours",
            "artifacts",
        },
        "candidate",
    )
    if candidate["schema"] != "wdw.public-candidate.v1" or not _valid_identifier(
        candidate["candidateId"], "candidate-"
    ):
        raise ValueError("unsupported public candidate")
    generated = _parse(str(candidate["generatedAt"]))
    observed = _parse(str(candidate["sourceObservedAt"]))
    eligible = _parse(str(candidate["eligibleAt"]))
    delay = candidate["releaseDelayHours"]
    hours = _validate_release_delay(delay)
    if eligible != generated + timedelta(hours=hours) or observed > generated:
        raise ValueError("candidate release delay metadata is inconsistent")
    if set(candidate["artifacts"]) != {"world.v1.json", "systems.v1.json"}:
        raise ValueError("candidate artifact allowlist mismatch")
    for artifact in candidate["artifacts"].values():
        _exact_keys(artifact, {"sha256", "bytes"}, "candidate artifact")
        if not _valid_integrity(artifact):
            raise ValueError("invalid candidate artifact integrity metadata")


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    _exact_keys(
        manifest,
        {
            "schema",
            "releaseId",
            "candidateId",
            "releasedAt",
            "sourceObservedAt",
            "releaseDelayHours",
            "artifacts",
        },
        "release manifest",
    )
    if (
        manifest["schema"] != MANIFEST_SCHEMA
        or not _valid_identifier(manifest["releaseId"], "release-")
        or not _valid_identifier(manifest["candidateId"], "candidate-")
    ):
        raise ValueError("unsupported public release manifest")
    _parse(str(manifest["releasedAt"]))
    _parse(str(manifest["sourceObservedAt"]))
    delay = manifest["releaseDelayHours"]
    _validate_release_delay(delay)
    if set(manifest["artifacts"]) != {"world.v1.json", "systems.v1.json"}:
        raise ValueError("release manifest artifact allowlist mismatch")
    for name, artifact in manifest["artifacts"].items():
        _exact_keys(artifact, {"path", "sha256", "bytes"}, "release artifact")
        expected_path = f"releases/{manifest['releaseId']}/{name}"
        if artifact["path"] != expected_path or not _valid_integrity(artifact):
            raise ValueError("invalid release artifact metadata")


@contextmanager
def _release_lock(state_root: Path):
    state_root = state_root.expanduser()
    if state_root.is_symlink():
        raise ValueError(f"refusing symlinked state root: {state_root}")
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / ".release.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def release_latest_eligible(
    *, state_root: Path, now: datetime, publish_root: Path | None = None
) -> dict[str, Any]:
    with _release_lock(state_root):
        return _release_latest_eligible_unlocked(
            state_root=state_root, now=now, publish_root=publish_root
        )


def _release_latest_eligible_unlocked(
    *, state_root: Path, now: datetime, publish_root: Path | None = None
) -> dict[str, Any]:
    eligible = _eligible_candidates(state_root, now)
    if not eligible:
        raise ReleaseNotReady("no sanitized candidate has completed its release delay")
    _, candidate_dir, candidate = eligible[0]
    _validate_candidate(candidate)
    payloads: dict[str, bytes] = {}
    for name, validator in (
        ("world.v1.json", validate_world),
        ("systems.v1.json", validate_systems),
    ):
        artifact_path = candidate_dir / name
        if artifact_path.is_symlink():
            raise ValueError(f"refusing symlinked candidate path: {artifact_path}")
        payload = artifact_path.read_bytes()
        expected = candidate["artifacts"][name]
        if _sha(payload) != expected["sha256"] or len(payload) != expected["bytes"]:
            raise ValueError(f"candidate artifact integrity check failed: {name}")
        validator(json.loads(payload))
        payloads[name] = payload
    if (
        _candidate_identifier(payloads, candidate["generatedAt"])
        != candidate["candidateId"]
    ):
        raise ValueError("candidate identity does not match its artifacts")
    systems = json.loads(payloads["systems.v1.json"])
    world = json.loads(payloads["world.v1.json"])
    if (
        systems["releaseDelayHours"] != candidate["releaseDelayHours"]
        or systems["generatedAt"] != candidate["generatedAt"]
        or world["generatedAt"] != candidate["generatedAt"]
        or systems["sourceObservedAt"] != candidate["sourceObservedAt"]
    ):
        raise ValueError("candidate and artifact metadata do not match")
    resident_statuses = [resident["status"] for resident in world["residents"]]
    expected_residents = {
        "total": len(resident_statuses),
        "active": resident_statuses.count("active"),
        "needsAttention": resident_statuses.count("needs-attention"),
    }
    if systems["residents"] != expected_residents:
        raise ValueError("systems resident aggregate does not match world artifact")
    if (
        candidate["releaseDelayHours"] == 24
        and _utc(now) < _parse(candidate["generatedAt"]) + PRODUCTION_DELAY
    ):
        raise ReleaseNotReady(
            "sanitized candidate has not completed its 24-hour release delay"
        )

    release_id = "release-" + _sha(candidate["candidateId"].encode())[:20]
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "releaseId": release_id,
        "candidateId": candidate["candidateId"],
        "releasedAt": _stamp(now),
        "sourceObservedAt": candidate["sourceObservedAt"],
        "releaseDelayHours": candidate["releaseDelayHours"],
        "artifacts": {
            name: {
                "path": f"releases/{release_id}/{name}",
                "sha256": candidate["artifacts"][name]["sha256"],
                "bytes": candidate["artifacts"][name]["bytes"],
            }
            for name in payloads
        },
    }
    validate_manifest(manifest)
    if _parse(manifest["releasedAt"]) < _parse(candidate["eligibleAt"]):
        raise ReleaseNotReady("sanitized candidate has not completed its release delay")
    state_publication_root = state_root / "published"
    if state_publication_root.is_symlink():
        raise ValueError(
            f"refusing symlinked publication root: {state_publication_root}"
        )
    state_manifest = state_publication_root / "manifest.v1.json"
    if state_manifest.is_symlink():
        raise ValueError(f"refusing symlinked release manifest: {state_manifest}")
    if state_manifest.exists():
        current = json.loads(state_manifest.read_text(encoding="utf-8"))
        validate_manifest(current)
        if current.get("candidateId") == candidate["candidateId"]:
            immutable_fields_match = (
                current["releaseId"] == release_id
                and current["sourceObservedAt"] == manifest["sourceObservedAt"]
                and current["releaseDelayHours"] == manifest["releaseDelayHours"]
                and current["artifacts"] == manifest["artifacts"]
            )
            released_at = _parse(current["releasedAt"])
            if (
                not immutable_fields_match
                or released_at < _parse(candidate["eligibleAt"])
                or released_at > _utc(now)
            ):
                raise ValueError(
                    "existing release manifest does not match the candidate"
                )
            manifest = current
    targets = [state_publication_root]
    if publish_root is not None:
        targets.append(publish_root)
    for root in targets:
        root = root.expanduser()
        if root.is_symlink():
            raise ValueError(f"refusing unsafe publication root: {root}")
        root = root.resolve(strict=False)
        root.mkdir(parents=True, exist_ok=True)
        releases_root = root / "releases"
        if releases_root.is_symlink():
            raise ValueError(f"refusing symlinked release root: {releases_root}")
        release_dir = releases_root / manifest["releaseId"]
        if release_dir.is_symlink():
            raise ValueError(f"refusing symlinked release directory: {release_dir}")
        for name, payload in payloads.items():
            destination = release_dir / name
            if destination.is_symlink():
                raise ValueError(f"immutable release collision: {destination}")
            if destination.exists() and destination.read_bytes() != payload:
                raise ValueError(f"immutable release collision: {destination}")
            if not destination.exists():
                _atomic_write(destination, payload)
        current_path = root / "manifest.v1.json"
        _atomic_write(current_path, _json_bytes(manifest))
    return manifest
