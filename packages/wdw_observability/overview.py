from __future__ import annotations

import argparse
import html
import json
from socketserver import ThreadingMixIn
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import WSGIServer, make_server

from .projections import PUBLIC_DELAY, models_experience, private_overview, public_systems_projection
from .refresh import ProjectionRefresher
from .store import OperatorStore

FRESH = timedelta(hours=24)
AGING = timedelta(days=7)
RESIDENT_REPOSITORIES = {
    "mini-me": "mini-me",
    "bridget": "bridget",
    "coach": "coach",
    "banjo": "banjo",
}
OVERVIEW_RECORD_KINDS = (
    "ResidentSnapshot",
    "MeaningfulActivity",
    "Ingestion",
    "EvaluationRun",
    "AttentionItem",
    "MorningInsightOperation",
)


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Keep one slow browser connection from blocking the operator surface."""

    daemon_threads = True


def _overview_records(store: OperatorStore) -> list[dict[str, Any]]:
    """Read the real overview projection from the durable store."""
    records: list[dict[str, Any]] = []
    for record_kind in OVERVIEW_RECORD_KINDS:
        records.extend(store.records(kind=record_kind, limit=1_000, mode="real"))
    return sorted(records, key=lambda row: str(row.get("occurred_at", "")), reverse=True)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result


def _freshness(value: Any, now: datetime) -> dict[str, str | None]:
    observed = _parse_timestamp(value)
    if observed is None:
        return {"state": "unknown", "label": "No timestamp reported", "at": None}
    age = max(now - observed, timedelta())
    if age < FRESH:
        state = "fresh"
    elif age < AGING:
        state = "aging"
    else:
        state = "stale"
    if age < timedelta(hours=1):
        label = f"{max(0, int(age.total_seconds() // 60))}m ago"
    elif age < timedelta(days=2):
        label = f"{int(age.total_seconds() // 3600)}h ago"
    else:
        label = f"{int(age.total_seconds() // 86400)}d ago"
    return {"state": state, "label": label, "at": observed.isoformat()}


def _safe_link(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    path = Path(candidate)
    if path.is_absolute() and path.exists():
        return path.resolve().as_uri()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https", "file"}:
        return candidate
    return None


def _record_link(row: Mapping[str, Any]) -> str | None:
    direct = _safe_link(row.get("source_ref"))
    if direct:
        return direct
    for field in ("links", "source_details", "provenance"):
        values = row.get(field)
        if isinstance(values, Mapping):
            for value in values.values():
                link = _safe_link(value)
                if link:
                    return link
    return None


def _resident_link(workspace: Path, resident_id: Any) -> str | None:
    folder = RESIDENT_REPOSITORIES.get(str(resident_id))
    if folder is None:
        return None
    path = workspace / folder
    return path.resolve().as_uri() if path.is_dir() else None


def _latest(rows: Iterable[Mapping[str, Any]], kind: str) -> Mapping[str, Any] | None:
    return next((row for row in rows if row.get("kind") == kind), None)


def build_private_view(
    records: Iterable[Mapping[str, Any]], *, now: datetime, workspace: Path
) -> dict[str, Any]:
    rows = list(records)
    result = private_overview(rows, now)
    residents: list[dict[str, Any]] = []
    for source in result["residents"]:
        row = dict(source)
        row["freshness"] = _freshness(
            row.get("last_meaningful_activity_at") or row.get("occurred_at"), now
        )
        row["deepLink"] = _resident_link(workspace, row.get("resident_id"))
        residents.append(row)
    result["residents"] = residents
    attention: list[dict[str, Any]] = []
    for source in result["needsHaley"]:
        row = dict(source)
        row["freshness"] = _freshness(row.get("updated_at") or row.get("occurred_at"), now)
        row["deepLink"] = _safe_link(row.get("deep_link")) or _resident_link(
            workspace, row.get("resident_id")
        )
        attention.append(row)
    result["needsHaley"] = attention

    activities: list[dict[str, Any]] = []
    for source in result["recentActivity"]:
        row = dict(source)
        row["freshness"] = _freshness(row.get("occurred_at"), now)
        row["deepLink"] = _record_link(row)
        activities.append(row)
    result["recentActivity"] = activities

    ingestions: list[dict[str, Any]] = []
    for source in result["recentIngestions"]:
        row = dict(source)
        row["observedFreshness"] = _freshness(
            row.get("completed_at") or row.get("occurred_at"), now
        )
        row["deepLink"] = _record_link(row)
        ingestions.append(row)
    result["recentIngestions"] = ingestions

    morning_insights: list[dict[str, Any]] = []
    for source in result["morningInsights"]:
        row = dict(source)
        row["freshness"] = _freshness(row.get("completed_at") or row.get("occurred_at"), now)
        row["deepLink"] = _record_link(row)
        morning_insights.append(row)
    result["morningInsights"] = morning_insights

    intelligence = list(result["intelligence"])
    latest_evaluation = intelligence[0] if intelligence else None
    result["models"] = models_experience(intelligence)
    latest_evidence = (
        latest_evaluation.get("evidence", {})
        if latest_evaluation and isinstance(latest_evaluation.get("evidence"), Mapping)
        else {}
    )
    raw_precision = latest_evaluation.get("precision_at_k") if latest_evaluation else None
    if isinstance(raw_precision, Mapping):
        precision_available = any(
            isinstance(item, Mapping) and item.get("state") == "available"
            for item in raw_precision.values()
        )
        precision_summary = next(
            (
                item.get("value")
                for item in raw_precision.values()
                if isinstance(item, Mapping) and item.get("state") == "available"
            ),
            None,
        )
        precision_state = "known" if precision_available else "insufficient-evidence"
    else:
        precision_summary = raw_precision
        reviewed = latest_evaluation.get("reviewed_count") if latest_evaluation else None
        precision_state = (
            "unknown" if reviewed is None else
            "insufficient-evidence" if reviewed == 0 else
            "known" if raw_precision is not None else "unknown"
        )
    result["intelligenceSummary"] = {
        "state": latest_evaluation.get("evidence_state", "unknown") if latest_evaluation else "unknown",
        "freshness": _freshness(latest_evaluation.get("occurred_at"), now) if latest_evaluation else _freshness(None, now),
        "thoughts": (latest_evaluation.get("thought_count") if latest_evaluation else None) or latest_evidence.get("thoughts"),
        "candidates": (latest_evaluation.get("candidate_count") if latest_evaluation else None) or latest_evidence.get("candidates"),
        "reviewed": (latest_evaluation.get("reviewed_count") if latest_evaluation else None) if latest_evaluation and latest_evaluation.get("reviewed_count") is not None else latest_evidence.get("reviewed"),
        "precisionAtK": precision_summary,
        "precisionAtKState": precision_state,
    }

    latest_activity = _latest(rows, "MeaningfulActivity")
    latest_ingestion = _latest(rows, "Ingestion")
    latest_morning = _latest(rows, "MorningInsightOperation")
    morning_stages = set((latest_morning or {}).get("stages") or ())
    morning_execution_state = (
        "failed"
        if "failed" in morning_stages
        else "incomplete"
        if "incomplete" in morning_stages
        else "completed"
        if "completed" in morning_stages
        else "pending"
        if latest_morning
        else "unknown"
    )
    ingestion_state = "unknown"
    if latest_ingestion:
        ingestion_state = (
            "attention"
            if latest_ingestion.get("errors") or latest_ingestion.get("status") in {"failed", "error"}
            else latest_ingestion.get("evidence_state", "unknown")
        )
    result["systemHealth"] = [
        {
            "name": "Resident evidence",
            "state": result["health"]["state"],
            "freshness": _freshness(
                max(
                    (
                        timestamp
                        for row in residents
                        if (timestamp := row.get("occurred_at")) is not None
                    ),
                    default=None,
                ),
                now,
            ),
            "detail": f"{len(residents)} resident snapshots" if residents else "No resident snapshots observed",
        },
        {
            "name": "Activity feed",
            "state": latest_activity.get("evidence_state", "unknown") if latest_activity else "unknown",
            "freshness": _freshness(latest_activity.get("occurred_at"), now) if latest_activity else _freshness(None, now),
            "detail": "Meaningful activity is available" if latest_activity else "No meaningful activity observed",
        },
        {
            "name": "Ingestion feed",
            "state": ingestion_state,
            "freshness": _freshness(
                (latest_ingestion or {}).get("completed_at") or (latest_ingestion or {}).get("occurred_at"), now
            ),
            "detail": f"Latest status: {latest_ingestion.get('status')}" if latest_ingestion else "No ingestion runs observed",
        },
        {
            "name": "Intelligence evaluation",
            "state": result["intelligenceSummary"]["state"],
            "freshness": result["intelligenceSummary"]["freshness"],
            "detail": "Evaluation evidence is available" if latest_evaluation else "No evaluation run observed",
        },
        {
            "name": "Morning insight delivery",
            "state": latest_morning.get("status", "unknown") if latest_morning else "unknown",
            "freshness": _freshness(
                (latest_morning or {}).get("completed_at") or (latest_morning or {}).get("occurred_at"), now
            ),
            "detail": (
                f"Execution {morning_execution_state} · "
                f"delivery {latest_morning.get('delivery_status', 'unknown')}"
                if latest_morning else "No morning insight operation observed"
            ),
        },
    ]
    return result


def build_public_view(records: Iterable[Mapping[str, Any]], *, now: datetime) -> dict[str, Any]:
    rows = list(records)
    eligible = [
        row for row in rows
        if (observed := _parse_timestamp(row.get("observed_at"))) is not None
        and observed + PUBLIC_DELAY <= now
    ]
    if not eligible:
        release_times = [
            observed + PUBLIC_DELAY
            for row in rows
            if (observed := _parse_timestamp(row.get("observed_at"))) is not None
        ]
        return {
            "schema": "wdw.systems-preview.v1",
            "available": False,
            "releaseDelayHours": PUBLIC_DELAY.total_seconds() / 3600,
            "nextReleaseAt": min(release_times).isoformat() if release_times else None,
            "reason": "No real observations have completed the public release delay.",
        }
    source_observed_at = max(
        observed
        for row in eligible
        if (observed := _parse_timestamp(row.get("observed_at"))) is not None
    )
    private = private_overview(eligible, source_observed_at)
    result = public_systems_projection(private, now=now)
    result["available"] = True
    return result


def _text(value: Any, fallback: str = "Unknown") -> str:
    return html.escape(fallback if value in (None, "") else str(value))


def _badge(state: Any) -> str:
    normalized = str(state or "unknown")
    return f'<span class="badge {html.escape(normalized)}">{html.escape(normalized.replace("-", " "))}</span>'


def _link(href: Any, label: str = "Open source") -> str:
    safe = _safe_link(href)
    if not safe:
        return ""
    return f'<a href="{html.escape(safe, quote=True)}">{html.escape(label)} ↗</a>'


def _empty(message: str) -> str:
    return f'<div class="empty">{html.escape(message)}</div>'


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _number(value: Any, digits: int = 3) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _text(value)
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def _structured(value: Any, fallback: str = "Not reported") -> str:
    if value is None or value == "" or value == [] or value == {}:
        return html.escape(fallback)
    if isinstance(value, (Mapping, list, tuple)):
        return html.escape(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return _text(value, fallback)


def _morning_insights_content(rows: Iterable[Mapping[str, Any]]) -> str:
    cards: list[str] = []
    for row in rows:
        insight = _mapping(row.get("insight"))
        evidence = _mapping(row.get("evidence"))
        failure = _mapping(row.get("failure"))
        identifiers = " · ".join(
            f"{label} {_text(row.get(field))}"
            for label, field in (
                ("invocation", "invocation_id"), ("output", "output_message_id"),
                ("delivery", "delivery_id"), ("transport", "transport_message_id"),
                ("external", "external_message_id"),
            )
            if row.get(field)
        ) or "No execution or delivery identifiers reported"
        cards.append(f"""
          <article class="morning-insight">
            <div>{_badge(row.get('status'))}{_badge(row.get('delivery_status'))}<strong>{_text(row.get('occurrence_id'), 'Unknown occurrence')}</strong></div>
            <h3>{_text(insight.get('text'), 'No insight text recorded')}</h3>
            <p><strong>Insight:</strong> {_text(insight.get('id'), 'Not reported')} · <strong>Evidence:</strong> {_structured(evidence.get('basis'))}</p>
            <p><strong>Source refs:</strong> {_structured(evidence.get('source_refs'))}</p>
            <p><strong>Personalization:</strong> {_structured(row.get('personalization'))}</p>
            <p><strong>Current state:</strong> {_structured(row.get('current_state'))}</p>
            <p><strong>Recent observations:</strong> {_structured(row.get('recent_observations'))}</p>
            <p><strong>Historical context:</strong> {_structured(row.get('historical_context'))}</p>
            <p><strong>Prediction:</strong> {_structured(row.get('prediction'))}</p>
            <p><strong>Runtime:</strong> {_text(row.get('provider'))} / {_text(row.get('model'))} / {_text(row.get('model_version'))}</p>
            <p><strong>Stages:</strong> {_structured(row.get('stages'))}</p>
            <p><strong>Warnings:</strong> {_structured(row.get('warnings'), 'None')} · <strong>Failure:</strong> {_structured(failure, 'None')}</p>
            <small>{html.escape(identifiers)} · {_text(_mapping(row.get('freshness')).get('label'))} {_link(row.get('deepLink'), 'Source')}</small>
          </article>
        """)
    content = "".join(cards) or _empty("No morning insight operation has been observed.")
    return f'<section><h2>Morning Insights</h2><div class="stack">{content}</div></section>'


def _models_content(models: Mapping[str, Any]) -> str:
    availability = _mapping(models.get("availability"))
    latest = _mapping(models.get("latest"))
    if not latest:
        return f"""
          <section><h2>Models</h2>{_empty(str(availability.get('reason') or 'No canonical evaluation run is available.'))}
          <p class="meta">Model-quality claims require a persisted canonical evaluation-run snapshot. Transient reports and similarity scores are diagnostic evidence, not quality measurements.</p></section>
        """

    readiness = _mapping(latest.get("readiness"))
    evidence = _mapping(latest.get("evidence"))
    dataset = _mapping(latest.get("dataset"))
    provenance = _mapping(latest.get("provenance"))
    reproducibility = _mapping(latest.get("reproducibility"))
    distribution = _mapping(latest.get("scoreDistribution"))
    history = _mapping(models.get("history"))
    precision = _mapping(latest.get("precisionAtK"))
    comparison = _mapping(history.get("comparison"))

    precision_html = "".join(
        (
            f'<article><span>P@{key}</span><strong>{_number(item.get("value"))}</strong>'
            f'<small>{_text(item.get("eligibleGroups"), "0")} fully labeled source rankings</small></article>'
            if item.get("state") == "available" and item.get("value") is not None
            else f'<article><span>P@{key}</span><strong>Unavailable</strong><small>{_text(item.get("reason"), "Human labels are insufficient for this K.")}</small></article>'
        )
        for key in ("1", "3", "5")
        for item in [_mapping(precision.get(key))]
    )
    model_labels = ", ".join(
        f'{_text(_mapping(model).get("name"))}@{_text(_mapping(model).get("version"))}'
        for model in _sequence(latest.get("models"))
    ) or "Unknown"
    analysis_versions = ", ".join(_text(value) for value in _sequence(latest.get("analysisVersions"))) or "Unknown"
    provenance_rows = [
        ("Run", latest.get("runId")), ("Evaluated", latest.get("evaluatedAt")),
        ("Dataset", f'{dataset.get("id", "Unknown")} @ {dataset.get("version", "Unknown")}'),
        ("Dataset population", f'{dataset.get("sourceCount", "Unknown")} sources · {dataset.get("candidateCount", "Unknown")} candidates'),
        ("Models", model_labels), ("Analysis versions", analysis_versions),
        ("Evaluation code", latest.get("evaluationCodeVersion")),
        ("Evidence owner/source", f'{provenance.get("owner", "Unknown")} · {provenance.get("evidenceSource", "Unknown")}'),
        ("Human labels", provenance.get("humanLabels")),
        ("Reproduction source", reproducibility.get("sourceRef")),
    ]
    provenance_html = "".join(
        f'<tr><th>{_text(label)}</th><td>{_text(value)}</td></tr>' for label, value in provenance_rows
    )
    bins_html = "".join(
        f'<tr><td>{_number(_mapping(item).get("lower"))}–{_number(_mapping(item).get("upper"))}</td><td>{_text(_mapping(item).get("count"))}</td></tr>'
        for item in _sequence(distribution.get("bins"))
    ) or '<tr><td colspan="2">No distribution bins recorded.</td></tr>'
    rank_html = "".join(
        f'<tr><td>{_text(row.get("rank"))}</td><td>{_text(row.get("candidates"))}</td><td>{_text(row.get("reviewed"))}</td>'
        f'<td>{_text(row.get("accepted"))}/{_text(row.get("rejected"))}/{_text(row.get("unsure"))}</td><td>{_number(row.get("meanScore"))}</td></tr>'
        for source in _sequence(latest.get("rankBehavior")) for row in [_mapping(source)]
    ) or '<tr><td colspan="5">No rank behavior recorded.</td></tr>'
    candidates_html = "".join(
        f'<tr><td>{_text(row.get("sourceThoughtId"))}</td><td>{_text(row.get("targetThoughtId"))}</td>'
        f'<td>{_text(row.get("rank"))}</td><td>{_number(row.get("score"))}</td><td>{_badge(row.get("reviewStatus"))}</td></tr>'
        for source in _sequence(latest.get("topCandidates")) for row in [_mapping(source)]
    ) or '<tr><td colspan="5">No top candidates recorded.</td></tr>'
    comparison_html = "".join(
        (
            f'<tr><td>P@{key}</td><td>{_number(item.get("current"))}</td><td>{_number(item.get("previous"))}</td><td>{_number(item.get("delta"))}</td></tr>'
            if item.get("state") == "available"
            else f'<tr><td>P@{key}</td><td colspan="3">Unavailable — {_text(item.get("reason"))}</td></tr>'
        )
        for key in ("1", "3", "5") for item in [_mapping(comparison.get(key))]
    )
    limitations_html = "".join(f"<li>{_text(item)}</li>" for item in _sequence(latest.get("limitations"))) or "<li>None recorded.</li>"
    return f"""
      <section><h2>Models</h2>
        <div class="model-heading"><div>{_badge(readiness.get('state'))} {_badge(readiness.get('verdict'))}</div><strong>{_text(latest.get('evaluationName'))} · {_text(latest.get('evaluationVersion'))}</strong></div>
        <p>{_text(readiness.get('reason'))}</p><p class="meta">{_text(latest.get('purpose'))}</p>
        <div class="metrics">
          <article><span>Thoughts</span><strong>{_text(evidence.get('thoughts'))}</strong></article><article><span>Candidates</span><strong>{_text(evidence.get('candidates'))}</strong></article>
          <article><span>Reviewed</span><strong>{_text(evidence.get('reviewed'))}</strong></article><article><span>Accepted</span><strong>{_text(evidence.get('accepted'))}</strong></article>
        </div><h3>Human-labeled precision</h3><div class="metrics">{precision_html}</div>
        <p class="note">Similarity scores show embedding proximity. They do not establish model quality without sufficient human relationship labels.</p>
        <div class="subgrid"><div><h3>Provenance &amp; reproducibility</h3><div class="table"><table class="compact"><tbody>{provenance_html}</tbody></table></div></div>
        <div><h3>Score distribution</h3><p>{_text(distribution.get('interpretation'))}</p><p class="meta">{_text(distribution.get('kind'))} · n={_text(distribution.get('count'))} · min {_number(distribution.get('min'))} · mean {_number(distribution.get('mean'))} · max {_number(distribution.get('max'))}</p><div class="table"><table class="compact"><thead><tr><th>Range</th><th>Count</th></tr></thead><tbody>{bins_html}</tbody></table></div></div></div>
        <h3>Rank behavior</h3><div class="table"><table><thead><tr><th>Rank</th><th>Candidates</th><th>Reviewed</th><th>Accepted / Rejected / Unsure</th><th>Mean score</th></tr></thead><tbody>{rank_html}</tbody></table></div>
        <h3>Top candidates</h3><div class="table"><table><thead><tr><th>Source thought</th><th>Target thought</th><th>Rank</th><th>Similarity</th><th>Human label</th></tr></thead><tbody>{candidates_html}</tbody></table></div>
        <h3>Historical comparison</h3><p class="meta">{_text(history.get('compatibleRuns'), '0')} compatible runs · {_text(history.get('excludedRuns'), '0')} excluded as incomparable · baseline {_text(history.get('baselineRunId'), 'none')}</p>
        <div class="table"><table class="compact"><thead><tr><th>Measure</th><th>Current</th><th>Previous</th><th>Delta</th></tr></thead><tbody>{comparison_html}</tbody></table></div>
        <h3>Limitations</h3><ul>{limitations_html}</ul>
      </section>
    """


def _private_content(view: Mapping[str, Any], scan_error: str | None) -> str:
    needs = view["needsHaley"]
    residents = view["residents"]
    activity = view["recentActivity"]
    ingestions = view["recentIngestions"]
    morning_insights = view["morningInsights"]
    intelligence = view["intelligenceSummary"]
    models = view["models"]
    health = view["systemHealth"]

    warning = (
        '<div class="warning"><strong>Source refresh failed.</strong> Showing the last durable observations. '
        f'<span>{html.escape(scan_error)}</span></div>'
        if scan_error else ""
    )
    needs_html = "".join(
        f'<article><div>{_badge(row.get("status"))}<strong>{_text(row.get("summary"), "Attention requested")}</strong></div>'
        f'<p>{_text(row.get("reason"), "No reason supplied")}</p>'
        f'<small>{_text(row.get("resident_id"))} · owner {_text(row.get("owner"))} · {_text(row.get("freshness", {}).get("label"))}</small> '
        f'{_link(row.get("deepLink"), "Inspect")}</article>'
        for row in needs
    ) or _empty("No open attention items require Haley.")
    residents_html = "".join(
        f'<tr><td><strong>{_text(row.get("display_name"), "Unnamed resident")}</strong><small>{_text(row.get("resident_id"))}</small></td>'
        f'<td>{_badge(row.get("state"))}</td><td>{_text(row.get("status_summary"), "No status summary")}</td>'
        f'<td>{_badge(row.get("freshness", {}).get("state"))} {_text(row.get("freshness", {}).get("label"))}</td>'
        f'<td>{_link(row.get("deepLink"), "Repository")}</td></tr>'
        for row in residents
    ) or '<tr><td colspan="5">No resident snapshots observed.</td></tr>'
    health_html = "".join(
        f'<article><div>{_badge(row.get("state"))}<strong>{_text(row.get("name"))}</strong></div>'
        f'<p>{_text(row.get("detail"))}</p><small>{_badge(row.get("freshness", {}).get("state"))} '
        f'{_text(row.get("freshness", {}).get("label"))}</small></article>'
        for row in health
    )
    activity_html = "".join(
        f'<article><div>{_badge(row.get("evidence_state"))}<strong>{_text(row.get("summary"), "Unlabelled activity")}</strong></div>'
        f'<p>{_text(row.get("resident_id"))} · {_text(row.get("activity_kind"))} · {_text(row.get("outcome"), "Outcome unknown")}</p>'
        f'<small>{_text(row.get("freshness", {}).get("label"))}</small> {_link(row.get("deepLink"))}</article>'
        for row in activity
    ) or _empty("No meaningful activity has been observed.")
    ingestion_html = "".join(
        f'<tr><td><strong>{_text(row.get("source_kind"), "Unknown source")}</strong><small>{_text(row.get("resident_id"))}</small></td>'
        f'<td>{_badge(row.get("status"))}</td><td>{_text(row.get("item_count"), "Not reported")}</td>'
        f'<td>{_badge(row.get("observedFreshness", {}).get("state"))} {_text(row.get("observedFreshness", {}).get("label"))}</td>'
        f'<td>{_link(row.get("deepLink"))}</td></tr>'
        for row in ingestions
    ) or '<tr><td colspan="5">No data ingestion runs have been observed.</td></tr>'
    precision = (
        _text(intelligence.get("precisionAtK"))
        if intelligence.get("precisionAtK") is not None
        else _text(intelligence.get("precisionAtKState"))
    )
    return f"""
      {warning}
      <section><h2>Needs Haley</h2><div class="cards">{needs_html}</div></section>
      <section><h2>Residents</h2><div class="table"><table><thead><tr><th>Resident</th><th>State</th><th>Status</th><th>Freshness</th><th>Deep link</th></tr></thead><tbody>{residents_html}</tbody></table></div></section>
      <section><h2>Intelligence Summary</h2><div class="metrics">
        <article><span>Thoughts</span><strong>{_text(intelligence.get("thoughts"))}</strong></article>
        <article><span>Candidates</span><strong>{_text(intelligence.get("candidates"))}</strong></article>
        <article><span>Reviewed</span><strong>{_text(intelligence.get("reviewed"))}</strong></article>
        <article><span>Precision@K</span><strong>{precision}</strong></article>
      </div><p class="meta">{_badge(intelligence.get("state"))} {_badge(intelligence.get("freshness", {}).get("state"))} {_text(intelligence.get("freshness", {}).get("label"))}</p></section>
      {_models_content(models)}
      {_morning_insights_content(morning_insights)}
      <section><h2>System Health</h2><div class="cards health">{health_html}</div></section>
      <section><h2>Recent Activity</h2><div class="stack">{activity_html}</div></section>
      <section><h2>Recent Data Ingestions</h2><div class="table"><table><thead><tr><th>Source</th><th>Status</th><th>Items</th><th>Freshness</th><th>Deep link</th></tr></thead><tbody>{ingestion_html}</tbody></table></div></section>
    """


def _public_content(view: Mapping[str, Any]) -> str:
    if not view.get("available"):
        release = view.get("nextReleaseAt")
        timing = f" Next release: {_text(release)}." if release else ""
        return f"""
          <section><h2>Public systems preview</h2>
          <div class="empty"><strong>Delayed projection not available yet.</strong><p>{_text(view.get('reason'))}{timing}</p></div>
          <p class="meta">This preview reads the real projection source and releases only allowlisted aggregate fields after {_text(view.get('releaseDelayHours'))} hours.</p></section>
        """
    residents = view.get("residents", {})
    intelligence = view.get("intelligence", {})
    precision = intelligence.get("precisionAtK")
    if precision is None:
        precision = intelligence.get("precisionAtKState")
    return f"""
      <section><h2>Public systems preview</h2>
      <p class="meta">Allowlisted aggregate projection · {_text(view.get('releaseDelayHours'))}h release delay · source observed {_text(view.get('sourceObservedAt'))}</p>
      <div class="metrics">
        <article><span>Residents</span><strong>{_text(residents.get('total'))}</strong></article>
        <article><span>Active</span><strong>{_text(residents.get('active'))}</strong></article>
        <article><span>Needs attention</span><strong>{_text(residents.get('needsAttention'))}</strong></article>
        <article><span>System state</span><strong>{_text(view.get('state'))}</strong></article>
      </div></section>
      <section><h2>Public intelligence</h2><div class="metrics">
        <article><span>Thoughts</span><strong>{_text(intelligence.get('thoughts'))}</strong></article>
        <article><span>Candidates</span><strong>{_text(intelligence.get('candidates'))}</strong></article>
        <article><span>Reviewed</span><strong>{_text(intelligence.get('reviewed'))}</strong></article>
        <article><span>Precision@K</span><strong>{_text(precision)}</strong></article>
      </div></section>
    """


def render_page(view: Mapping[str, Any], *, mode: str, scan_error: str | None = None) -> bytes:
    content = _private_content(view, scan_error) if mode == "private" else _public_content(view)
    private_active = "active" if mode == "private" else ""
    public_active = "active" if mode == "public" else ""
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wonderful Digital World · Command Center</title>
<style>
:root{{--ink:#16211d;--muted:#617069;--paper:#f4f2ea;--panel:#fffdf7;--line:#d9d6ca;--green:#296248;--amber:#976515;--red:#9b3f38;--blue:#335f7b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}header,main{{max-width:1240px;margin:auto}}header{{padding:38px 34px 22px;display:flex;justify-content:space-between;gap:24px;align-items:end}}h1{{font:700 34px/1.1 Georgia,serif;margin:4px 0}}h2{{font:700 23px/1.2 Georgia,serif;margin:0 0 16px}}h3{{font:700 17px/1.2 Georgia,serif;margin:24px 0 10px}}.eyebrow,.meta,small{{color:var(--muted)}}nav{{display:flex;background:#e7e4da;border-radius:10px;padding:4px}}nav a{{padding:8px 13px;border-radius:7px;color:var(--ink);text-decoration:none}}nav a.active{{background:var(--panel);box-shadow:0 1px 3px #0002}}main{{padding:0 34px 54px}}section{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px;margin:0 0 18px}}.cards,.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.cards article,.stack article,.metrics article{{border:1px solid var(--line);border-radius:10px;padding:14px}}article div{{display:flex;gap:8px;align-items:center}}article p{{margin:9px 0;color:var(--muted)}}.metrics article{{display:flex;flex-direction:column}}.metrics strong{{font:700 26px/1.2 Georgia,serif;margin-top:6px}}.stack{{display:grid;gap:10px}}.subgrid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.model-heading{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}.note{{border-left:3px solid var(--amber);padding:9px 12px;background:#fff8e8;color:var(--muted)}}.table{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:760px}}table.compact{{min-width:420px}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}td small{{display:block}}a{{color:var(--blue)}}.badge{{display:inline-block;padding:2px 7px;border-radius:999px;background:#e3e5e2;color:#45514c;font-size:11px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}}.badge.known,.badge.fresh,.badge.active,.badge.complete,.badge.completed,.badge.delivered,.badge.success,.badge.ready,.badge.measured,.badge.available{{background:#d9eadf;color:var(--green)}}.badge.partial,.badge.aging,.badge.needs-attention,.badge.partial-evidence,.badge.evidence-limited,.badge.incomplete,.badge.queued,.badge.pending{{background:#f2e4c4;color:var(--amber)}}.badge.stale,.badge.attention,.badge.failed,.badge.error,.badge.pending-human-review,.badge.unavailable{{background:#f1d8d5;color:var(--red)}}.empty,.warning{{border:1px dashed var(--line);border-radius:10px;padding:18px;color:var(--muted)}}.warning{{border-style:solid;border-color:#d7b56d;background:#fff5dc;margin-bottom:18px}}.warning span{{display:block;font-size:12px;margin-top:4px}}@media(max-width:800px){{header{{align-items:start;flex-direction:column}}.cards,.metrics,.subgrid{{grid-template-columns:1fr 1fr}}}}@media(max-width:520px){{.cards,.metrics,.subgrid{{grid-template-columns:1fr}}header,main{{padding-left:18px;padding-right:18px}}}}
</style></head><body><header><div><div class="eyebrow">OPERATOR OVERVIEW · REAL OBSERVATIONS</div><h1>Command Center</h1><div class="meta">Generated {_text(view.get('generatedAt'), 'now')} · {_text(mode.title())} view</div></div><nav aria-label="Preview mode"><a class="{private_active}" href="/overview?view=private">Private</a><a class="{public_active}" href="/overview?view=public">Public preview</a></nav></header><main>{content}</main></body></html>"""
    return document.encode("utf-8")


def create_app(
    store: OperatorStore,
    *,
    workspace: Path,
    now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    scan_error: str | None = None,
    refresher: ProjectionRefresher | None = None,
) -> Callable[..., list[bytes]]:
    def application(environ: Mapping[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        path = environ.get("PATH_INFO", "/")
        if path == "/":
            start_response("302 Found", [("Location", "/overview?view=private"), ("Content-Length", "0")])
            return [b""]
        if path not in {"/overview", "/api/overview"}:
            body = b"Not found"
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
        requested = parse_qs(str(environ.get("QUERY_STRING", ""))).get("view", ["private"])[0]
        mode = requested if requested in {"private", "public"} else "private"
        if refresher is not None:
            refresher.refresh()
        now = now_provider()
        records = _overview_records(store)
        view = (
            build_private_view(records, now=now, workspace=workspace)
            if mode == "private"
            else build_public_view(records, now=now)
        )
        if mode == "private":
            view["projection"] = refresher.status() if refresher else {
                "state": "static", "lastAttemptAt": None, "lastSuccessAt": None, "error": scan_error
            }
        if path == "/api/overview":
            body = json.dumps(view, separators=(",", ":"), sort_keys=True).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            refresh_error = _mapping(view.get("projection")).get("error") if mode == "private" else None
            body = render_page(view, mode=mode, scan_error=str(refresh_error) if refresh_error else scan_error)
            content_type = "text/html; charset=utf-8"
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"),
            ("X-Content-Type-Options", "nosniff"),
        ]
        start_response("200 OK", headers)
        return [body]

    return application


def main(argv: list[str] | None = None) -> int:
    default_workspace = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Run the private WDW Command Center overview.")
    parser.add_argument("--workspace", type=Path, default=default_workspace)
    parser.add_argument("--database", type=Path, default=Path("wdw-command-center.sqlite3"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Command Center only binds to a loopback host")
    if args.refresh_seconds <= 0:
        parser.error("--refresh-seconds must be positive")

    store = OperatorStore(args.database)
    store.purge_fixtures()
    refresher = ProjectionRefresher(
        store, args.workspace, interval_seconds=args.refresh_seconds
    )
    refresher.refresh(force=True)
    application = create_app(store, workspace=args.workspace, refresher=refresher)
    with make_server(
        args.host,
        args.port,
        application,
        server_class=ThreadingWSGIServer,
    ) as server:
        print(f"Command Center: http://{args.host}:{args.port}/overview?view=private")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
