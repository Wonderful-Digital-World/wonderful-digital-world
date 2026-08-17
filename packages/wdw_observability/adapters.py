from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.request import urlopen

from .contracts import (
    EvaluationRun, EvidenceState, Ingestion, MeaningfulActivity, ModelVersion,
    ResidentSnapshot, ResidentState, ReviewDecision, ReviewOutcome,
)

DISPLAY_NAMES = {"bridget": "Bridget", "coach": "Coach", "mini-me": "Mini Me", "banjo": "Banjo"}
CONTRACT_VERSION = "1.0"


def _time(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def _parse_time(value: Any, fallback: datetime) -> datetime:
    if not value:
        return fallback
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("boundary timestamps must be timezone-aware")
    return parsed


def _boundary(value: Mapping[str, Any], owner: str) -> None:
    if value.get("contractVersion") != CONTRACT_VERSION or value.get("owner") != owner:
        raise ValueError(f"unsupported {owner} observability boundary")


def banjo_activity_records(value: Mapping[str, Any], observed_at: datetime) -> list[MeaningfulActivity]:
    _boundary(value, "banjo")
    occurred = _parse_time(value.get("occurredAt"), observed_at)
    links = value.get("links") if isinstance(value.get("links"), Mapping) else {}
    return [MeaningfulActivity(
        record_id=str(value["eventId"]), occurred_at=occurred, observed_at=observed_at,
        evidence_state=EvidenceState.KNOWN, resident_id="banjo",
        kind=str(value.get("activityType", "engineering.work_item")),
        summary=str(value.get("summary", "")), outcome=str(value.get("outcome", "unknown")),
        source_ref=str(links.get("workItem")) if links.get("workItem") else None,
        contract_version=CONTRACT_VERSION, canonical_owner="banjo",
        actor=str(value.get("actor", "banjo")), links=dict(links),
        evidence_links=tuple(str(item) for item in value.get("evidenceLinks", [])),
        compute_provenance=dict(value.get("computeProvenance") or {}),
    )]


def bridget_ingestion_records(value: Mapping[str, Any], observed_at: datetime) -> list[Ingestion]:
    _boundary(value, "bridget")
    records: list[Ingestion] = []
    for run in value.get("runs", []):
        _boundary(run, "bridget")
        started = _parse_time(run.get("startedAt"), observed_at)
        completed = _parse_time(run.get("completedAt"), observed_at) if run.get("completedAt") else None
        counts = run.get("counts") or {}
        source = run.get("source") or {}
        loaded = counts.get("loaded")
        records.append(Ingestion(
            record_id=str(run["ingestionId"]), occurred_at=completed or started,
            observed_at=observed_at, evidence_state=EvidenceState.KNOWN,
            resident_id="bridget", source_kind=str(source.get("type", "unknown")),
            item_count=int(loaded) if loaded is not None else None, status=str(run.get("status", "unknown")),
            contract_version=CONTRACT_VERSION, canonical_owner="bridget",
            started_at=started, completed_at=completed, source_details=dict(source),
            emitted_count=int(counts["emitted"]) if counts.get("emitted") is not None else None,
            loaded_count=int(loaded) if loaded is not None else None,
            freshness=dict(run.get("freshness") or {}), processor=dict(run.get("processor") or {}),
            schema_version=str(run["schemaVersion"]) if run.get("schemaVersion") else None,
            warnings=tuple(str(item) for item in run.get("warnings", [])),
            errors=tuple(str(item) for item in run.get("errors", [])),
            provenance=dict(run.get("provenance") or {}),
        ))
    return records


def mini_me_review_evaluation_records(value: Mapping[str, Any], observed_at: datetime) -> list[Any]:
    boundary_version = str(value.get("contractVersion", ""))
    if boundary_version not in {"1.0", "2.0"} or value.get("owner") != "mini-me":
        raise ValueError("unsupported mini-me observability boundary")
    generated = _parse_time(value.get("generatedAt"), observed_at)
    records: list[Any] = []
    for evaluation in value.get("evaluations", []):
        if evaluation.get("evaluationRunId"):
            records.append(_canonical_evaluation_run(evaluation, generated, observed_at))
            continue
        occurred = _parse_time(evaluation.get("occurredAt"), generated)
        reviewed = evaluation.get("reviewedCount")
        records.append(EvaluationRun(
            record_id=str(evaluation["evaluationId"]), occurred_at=occurred,
            observed_at=observed_at, evidence_state=EvidenceState.KNOWN,
            model_id=str(evaluation.get("modelId", "")),
            model_version=str(evaluation.get("modelVersion", "")),
            thought_count=_optional_int(evaluation.get("thoughtCount")),
            candidate_count=_optional_int(evaluation.get("candidateCount")),
            reviewed_count=_optional_int(reviewed),
            mean_similarity=_optional_float(evaluation.get("meanSimilarity")),
            precision_at_k=_optional_float(evaluation.get("precisionAtK")),
            median_similarity=_optional_float(evaluation.get("medianSimilarity")),
            min_similarity=_optional_float(evaluation.get("minSimilarity")),
            max_similarity=_optional_float(evaluation.get("maxSimilarity")),
            score_distribution=dict(evaluation.get("scoreDistribution") or {}),
            rank_behavior=dict(evaluation.get("rankBehavior") or {}),
            reciprocal_graph=dict(evaluation.get("reciprocalGraph") or {}),
            analysis_version=(str(evaluation["analysisVersion"]) if evaluation.get("analysisVersion") else None),
            readiness=str(evaluation.get("readiness", "unknown")),
            top_candidates=tuple(evaluation.get("topCandidates") or ()),
            source_ref=(str(evaluation["sourceRef"]) if evaluation.get("sourceRef") else None),
            canonical_owner="mini-me",
            read_only=True, contract_version=CONTRACT_VERSION,
        ))
    for review in value.get("reviews", []):
        occurred = _parse_time(review.get("occurredAt"), generated)
        records.append(ReviewDecision(
            record_id=str(review["decisionId"]), occurred_at=occurred, observed_at=observed_at,
            evidence_state=EvidenceState.KNOWN, evaluation_id=str(review.get("evaluationId", "")),
            candidate_id=str(review.get("subjectId", "")), reviewer=str(review.get("reviewer", "unknown")),
            outcome=ReviewOutcome(str(review["outcome"])), note=review.get("note"),
            contract_version=CONTRACT_VERSION, canonical_owner="mini-me", read_only=True,
            review_kind=str(review.get("reviewKind", "artifact-lifecycle")),
            subject_kind=str(review.get("subjectKind", "artifact")),
            request_id=str(review["requestId"]) if review.get("requestId") else None,
        ))
    return records


def _canonical_evaluation_run(
    evaluation: Mapping[str, Any], generated: datetime, observed_at: datetime,
) -> EvaluationRun:
    occurred = _parse_time(evaluation.get("evaluatedAt"), generated)
    evidence = dict(evaluation.get("evidence") or {})
    distribution = dict(evaluation.get("scoreDistribution") or {})
    models = tuple(dict(item) for item in evaluation.get("models", []) if isinstance(item, Mapping))
    first_model = models[0] if models else {}
    reproducibility = dict(evaluation.get("reproducibility") or {})
    provenance = dict(evaluation.get("provenance") or {})
    return EvaluationRun(
        record_id=str(evaluation["evaluationRunId"]), occurred_at=occurred,
        observed_at=observed_at, evidence_state=EvidenceState.KNOWN,
        model_id=str(first_model.get("name", "")),
        model_version=str(first_model.get("version", "")),
        thought_count=_optional_int(evidence.get("thoughts")),
        candidate_count=_optional_int(evidence.get("candidates")),
        reviewed_count=_optional_int(evidence.get("reviewed")),
        mean_similarity=_optional_float(distribution.get("mean")),
        precision_at_k=dict(evaluation.get("precisionAtK") or {}),
        min_similarity=_optional_float(distribution.get("min")),
        max_similarity=_optional_float(distribution.get("max")),
        score_distribution=distribution,
        rank_behavior=tuple(
            dict(item) for item in evaluation.get("rankBehavior", []) if isinstance(item, Mapping)
        ),
        analysis_version=(
            str(evaluation.get("analysisVersions", [""])[0])
            if evaluation.get("analysisVersions") else None
        ),
        readiness=dict(evaluation.get("readiness") or {}),
        top_candidates=tuple(
            dict(item) for item in evaluation.get("topCandidates", []) if isinstance(item, Mapping)
        ),
        source_ref=str(reproducibility.get("sourceRef")) if reproducibility.get("sourceRef") else None,
        canonical_owner=str(provenance.get("owner", "mini-me")), read_only=True,
        contract_version=str(evaluation.get("contractVersion", "2.0")),
        evaluation_name=str(evaluation.get("evaluationName", "")) or None,
        evaluation_version=str(evaluation.get("evaluationVersion", "")) or None,
        purpose=str(evaluation.get("purpose", "")) or None,
        dataset=dict(evaluation.get("dataset") or {}),
        analysis_versions=tuple(str(item) for item in evaluation.get("analysisVersions", [])),
        models=models,
        evaluation_code_version=str(evaluation.get("evaluationCodeVersion", "")) or None,
        reproducibility=reproducibility, evidence=evidence,
        limitations=tuple(str(item) for item in evaluation.get("limitations", [])),
        provenance=provenance,
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _json_file(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def workspace_records(workspace: Path) -> list[Any]:
    """Read repository-owned, versioned boundaries into read-only projections."""
    now = datetime.now(timezone.utc)
    records: list[Any] = []
    for slug, name in DISPLAY_NAMES.items():
        repo = workspace / slug
        descriptor = repo / "resident.json"
        fallback = repo / "README.md"
        source = descriptor if descriptor.exists() else fallback
        if not source.exists():
            records.append(ResidentSnapshot(f"resident-{slug}-missing", now, now, EvidenceState.UNKNOWN, slug, name, ResidentState.UNAVAILABLE, "Repository or descriptor not observed.", None))
            continue
        occurred = _time(source)
        age_days = (now - occurred).days
        evidence = EvidenceState.STALE if age_days >= 7 else (EvidenceState.KNOWN if descriptor.exists() else EvidenceState.PARTIAL)
        state = ResidentState.IDLE if descriptor.exists() else ResidentState.UNAVAILABLE
        summary = f"Descriptor observed; latest source evidence is {age_days} days old." if descriptor.exists() else "Repository observed, but no resident descriptor or activity feed is available."
        records.append(ResidentSnapshot(f"resident-{slug}-{source.stat().st_mtime_ns}", occurred, now, evidence, slug, name, state, summary, occurred))

    report = workspace / "the-human-model" / "modeling" / "reports" / "readiness_report.md"
    if report.exists():
        occurred = _time(report)
        records.append(ModelVersion(f"human-model-readiness-{report.stat().st_mtime_ns}", occurred, now, EvidenceState.KNOWN, "human-model-readiness", "report-artifact", "Readiness model/data system", "observed"))

    activity_path = Path(os.environ.get("WDW_BANJO_ACTIVITY_LOG", workspace / "banjo" / ".banjo" / "activity-v1.jsonl"))
    if activity_path.is_file():
        for line in activity_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.extend(banjo_activity_records(json.loads(line), now))

    ingestion_path = Path(
        os.environ.get(
            "WDW_BRIDGET_INGESTION_BOUNDARY",
            workspace / "bridget" / ".human_model_ingestion_v1.json",
        )
    )
    if ingestion_path.is_file():
        records.extend(bridget_ingestion_records(_json_file(ingestion_path), now))

    mini_me_path = os.environ.get("WDW_MINI_ME_REVIEW_EVALUATION")
    mini_me_url = os.environ.get("WDW_MINI_ME_REVIEW_EVALUATION_URL")
    if mini_me_path and Path(mini_me_path).is_file():
        records.extend(mini_me_review_evaluation_records(_json_file(Path(mini_me_path)), now))
    elif mini_me_url:
        with urlopen(mini_me_url, timeout=2) as response:
            records.extend(mini_me_review_evaluation_records(json.load(response), now))
    return records
