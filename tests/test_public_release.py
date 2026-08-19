from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from wdw_observability import publish_public
from wdw_observability.public_release import (
    PRODUCTION_DELAY,
    ReleaseNotReady,
    build_artifacts,
    create_candidate,
    release_delay_from_environment,
    release_latest_eligible,
)

NOW = datetime(2026, 8, 19, 8, 15, tzinfo=UTC)
RECORDS = [
    {
        "kind": "ResidentSnapshot",
        "resident_id": "bridget",
        "evidence_state": "known",
        "observed_at": "2026-08-19T08:00:00Z",
        "state": "active",
        "display_name": "PRIVATE BRIDGET ALIAS",
        "source_ref": "/Users/private/secret.json",
    },
    {
        "kind": "ResidentSnapshot",
        "resident_id": "coach",
        "evidence_state": "known",
        "observed_at": "2026-08-19T08:01:00Z",
        "state": "needs-attention",
    },
    {
        "kind": "EvaluationRun",
        "observed_at": "2026-08-19T08:02:00Z",
        "thought_count": 12,
        "candidate_count": 3,
        "reviewed_count": 2,
        "mean_similarity": 0.75,
        "precision_at_k": 0.5,
    },
]


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def _candidate_directory(state_root: Path, candidate: dict[str, object]) -> Path:
    return state_root / "candidates" / str(candidate["candidateId"])


def test_build_artifacts_is_an_allowlisted_sanitized_projection() -> None:
    artifacts = build_artifacts(RECORDS, generated_at=NOW)

    world = artifacts["world.v1.json"]
    systems = artifacts["systems.v1.json"]
    assert world["residents"][0] == {
        "residentId": "bridget",
        "name": "Bridget",
        "role": "Orchestrator",
        "placeId": "workshop",
        "status": "active",
    }
    assert systems["residents"] == {"total": 2, "active": 1, "needsAttention": 1}
    assert systems["intelligence"]["precisionAtKState"] == "available"
    serialized = json.dumps(artifacts)
    assert "PRIVATE BRIDGET ALIAS" not in serialized
    assert "/Users/private" not in serialized


def test_stale_canonical_bridget_is_published_as_unavailable() -> None:
    stale = {
        **RECORDS[0],
        "evidence_state": "stale",
        "state": "idle",
    }

    artifacts = build_artifacts([stale], generated_at=NOW)

    assert artifacts["world.v1.json"]["residents"] == [
        {
            "residentId": "bridget",
            "name": "Bridget",
            "role": "Orchestrator",
            "placeId": "workshop",
            "status": "unavailable",
        }
    ]
    assert artifacts["world.v1.json"]["status"] == "partial"
    assert artifacts["systems.v1.json"]["state"] == "unknown"


def test_missing_canonical_bridget_fails_closed() -> None:
    with pytest.raises(ValueError, match="canonical Bridget state unavailable"):
        build_artifacts([], generated_at=NOW)


def test_release_enforces_delay_integrity_and_immutable_paths(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    publish_root = tmp_path / "site" / "projections" / "wdw"
    candidate = create_candidate(
        RECORDS, state_root=state_root, now=NOW, delay=PRODUCTION_DELAY
    )

    with pytest.raises(ReleaseNotReady):
        release_latest_eligible(
            state_root=state_root, now=NOW + PRODUCTION_DELAY - timedelta(seconds=1)
        )

    manifest = release_latest_eligible(
        state_root=state_root,
        now=NOW + PRODUCTION_DELAY,
        publish_root=publish_root,
    )
    assert manifest["candidateId"] == candidate["candidateId"]
    assert manifest["releaseDelayHours"] == 24
    for integrity in manifest["artifacts"].values():
        payload = (publish_root / integrity["path"]).read_bytes()
        assert len(payload) == integrity["bytes"]
        assert hashlib.sha256(payload).hexdigest() == integrity["sha256"]
    assert json.loads((publish_root / "manifest.v1.json").read_text()) == manifest

    repeated = release_latest_eligible(
        state_root=state_root,
        now=NOW + PRODUCTION_DELAY + timedelta(hours=1),
        publish_root=publish_root,
    )
    assert repeated == manifest


def test_tampered_candidate_is_not_released(tmp_path: Path) -> None:
    candidate = create_candidate(
        RECORDS, state_root=tmp_path, now=NOW, delay=PRODUCTION_DELAY
    )
    artifact = _candidate_directory(tmp_path, candidate) / "world.v1.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")

    with pytest.raises(ValueError, match="integrity check failed"):
        release_latest_eligible(state_root=tmp_path, now=NOW + PRODUCTION_DELAY)


def test_semantic_cross_artifact_mismatch_is_not_released(tmp_path: Path) -> None:
    candidate = create_candidate(
        RECORDS, state_root=tmp_path, now=NOW, delay=PRODUCTION_DELAY
    )
    directory = _candidate_directory(tmp_path, candidate)
    systems_path = directory / "systems.v1.json"
    systems = json.loads(systems_path.read_text())
    systems["residents"]["active"] = 0
    payload = _canonical(systems)
    systems_path.write_bytes(payload)

    candidate_path = directory / "candidate.json"
    stored_candidate = json.loads(candidate_path.read_text())
    stored_candidate["artifacts"]["systems.v1.json"] = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    identity = systems_path.read_bytes() + (directory / "world.v1.json").read_bytes()
    identity += stored_candidate["generatedAt"].encode("utf-8")
    candidate_id = f"candidate-{hashlib.sha256(identity).hexdigest()[:20]}"
    stored_candidate["candidateId"] = candidate_id
    candidate_path.write_bytes(_canonical(stored_candidate))
    directory = directory.rename(directory.parent / candidate_id)

    with pytest.raises(ValueError, match="aggregate does not match"):
        release_latest_eligible(state_root=tmp_path, now=NOW + PRODUCTION_DELAY)


def test_candidate_files_cannot_be_replaced_on_regeneration(tmp_path: Path) -> None:
    candidate = create_candidate(
        RECORDS, state_root=tmp_path, now=NOW, delay=PRODUCTION_DELAY
    )
    artifact = _candidate_directory(tmp_path, candidate) / "world.v1.json"
    artifact.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="immutable candidate collision"):
        create_candidate(RECORDS, state_root=tmp_path, now=NOW, delay=PRODUCTION_DELAY)


def test_existing_manifest_for_candidate_must_match_immutable_release(
    tmp_path: Path,
) -> None:
    create_candidate(RECORDS, state_root=tmp_path, now=NOW, delay=PRODUCTION_DELAY)
    release_latest_eligible(state_root=tmp_path, now=NOW + PRODUCTION_DELAY)
    manifest_path = tmp_path / "published" / "manifest.v1.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"]["world.v1.json"]["sha256"] = "0" * 64
    manifest_path.write_bytes(_canonical(manifest))

    with pytest.raises(ValueError, match="does not match the candidate"):
        release_latest_eligible(
            state_root=tmp_path,
            now=NOW + PRODUCTION_DELAY + timedelta(hours=1),
        )


def test_candidate_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    candidate = create_candidate(
        RECORDS, state_root=tmp_path, now=NOW, delay=PRODUCTION_DELAY
    )
    directory = _candidate_directory(tmp_path, candidate)
    artifact = directory / "world.v1.json"
    replacement = directory / "replacement.json"
    replacement.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(replacement.name)

    with pytest.raises(ValueError, match="symlinked candidate path|integrity"):
        release_latest_eligible(state_root=tmp_path, now=NOW + PRODUCTION_DELAY)


def test_delay_override_is_limited_to_non_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WDW_ENV", "production")
    with pytest.raises(ValueError, match="fixed at 24 hours"):
        release_delay_from_environment(1)

    monkeypatch.setenv("WDW_ENV", "test")
    assert release_delay_from_environment(1) == timedelta(hours=1)


def test_publish_receipt_identifies_the_candidate_actually_released(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generated = {"candidateId": "candidate-new"}
    released = {
        "candidateId": "candidate-matured",
        "releaseId": "release-matured",
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publish-public",
            "--workspace",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--website-repo",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(publish_public, "_repository_root", lambda path: tmp_path)
    monkeypatch.setattr(publish_public, "workspace_records", lambda path: [])
    monkeypatch.setattr(publish_public, "create_candidate", lambda *args, **kwargs: generated)
    monkeypatch.setattr(
        publish_public,
        "release_latest_eligible",
        lambda **kwargs: released,
    )
    monkeypatch.setattr(publish_public, "_changed_projection_paths", lambda repo: [])

    publish_public.main()

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "published"
    assert receipt["candidateId"] == "candidate-matured"
    assert receipt["generatedCandidateId"] == "candidate-new"
