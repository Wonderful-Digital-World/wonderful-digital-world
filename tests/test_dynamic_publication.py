from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wdw_observability.projections import (
    PUBLIC_DELAY,
    _sha256,
    assert_public_shape,
    public_snapshot,
)


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


def private_projection() -> dict[str, object]:
    return {
        "schema": "wdw.operator-overview.v1",
        "generatedAt": NOW.isoformat(),
        "needsHaley": [{"resident_id": "private"}],
        "residents": [
            {"resident_id": "a", "name": "Private A", "state": "active"},
            {"resident_id": "b", "name": "Private B", "state": "idle"},
        ],
        "intelligence": [
            {
                "thought_count": 12,
                "candidate_count": 3,
                "reviewed_count": 0,
                "mean_similarity": 0.5,
                "precision_at_k": None,
            }
        ],
        "health": {"state": "known"},
    }


def test_snapshot_is_safe_hashed_and_delayed() -> None:
    snapshot = public_snapshot(private_projection(), generated_at=NOW)

    assert snapshot["eligibleAt"] == (NOW + PUBLIC_DELAY).isoformat()
    assert snapshot["contentHash"] == _sha256(snapshot["payload"])
    unsigned = {key: value for key, value in snapshot.items() if key != "snapshotId"}
    assert snapshot["snapshotId"] == _sha256(unsigned)
    assert snapshot["payload"]["residents"] == {
        "total": 2,
        "active": 1,
        "needsAttention": 1,
    }
    serialized = str(snapshot)
    assert "Private A" not in serialized
    assert "resident_id" not in serialized
    assert_public_shape(snapshot["payload"])


def test_snapshot_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        public_snapshot(private_projection(), generated_at=datetime(2026, 8, 23))


def test_snapshot_delay_cannot_be_shortened_or_extended() -> None:
    with pytest.raises(ValueError, match="exactly 24 hours"):
        public_snapshot(
            private_projection(), generated_at=NOW, delay=timedelta(hours=23)
        )


def test_snapshot_rejects_non_finite_public_numbers() -> None:
    private = private_projection()
    private["intelligence"][0]["mean_similarity"] = float("nan")

    with pytest.raises(ValueError, match="JSON compliant"):
        public_snapshot(private, generated_at=NOW)


def test_snapshot_id_is_stable_for_retry_and_changes_for_new_generation() -> None:
    first = public_snapshot(private_projection(), generated_at=NOW)
    retry = public_snapshot(private_projection(), generated_at=NOW)
    later = public_snapshot(
        private_projection(), generated_at=NOW + timedelta(minutes=15)
    )

    assert first == retry
    assert later["snapshotId"] != first["snapshotId"]
