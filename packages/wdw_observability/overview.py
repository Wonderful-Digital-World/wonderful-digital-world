from __future__ import annotations

import argparse
import html
import json
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server

from .adapters import workspace_records
from .projections import PUBLIC_DELAY, private_overview, public_systems_projection
from .store import OperatorStore

FRESH = timedelta(hours=24)
AGING = timedelta(days=7)
RESIDENT_REPOSITORIES = {
    "mini-me": "mini-me",
    "bridget": "bridget",
    "coach": "coach",
    "banjo": "banjo",
    "human-model": "human-model",
}
OVERVIEW_RECORD_KINDS = (
    "ResidentSnapshot",
    "MeaningfulActivity",
    "Ingestion",
    "EvaluationRun",
)


def _overview_records(store: OperatorStore) -> list[dict[str, Any]]:
    """Read WP1 records without losing the activity payload's domain kind."""
    records: list[dict[str, Any]] = []
    for record_kind in OVERVIEW_RECORD_KINDS:
        for source in store.records(kind=record_kind, limit=1_000, mode="real"):
            row = dict(source)
            if record_kind == "MeaningfulActivity":
                row["activity_kind"] = row.get("kind")
            row["kind"] = record_kind
            records.append(row)
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
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https", "file"}:
        return candidate
    path = Path(candidate)
    if path.is_absolute() and path.exists():
        return path.resolve().as_uri()
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
    result["needsHaley"] = [row for row in residents if row.get("state") == "needs-attention"]

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

    intelligence = list(result["intelligence"])
    latest_evaluation = intelligence[0] if intelligence else None
    result["intelligenceSummary"] = {
        "state": latest_evaluation.get("evidence_state", "unknown") if latest_evaluation else "unknown",
        "freshness": _freshness(latest_evaluation.get("occurred_at"), now) if latest_evaluation else _freshness(None, now),
        "thoughts": latest_evaluation.get("thought_count") if latest_evaluation else None,
        "candidates": latest_evaluation.get("candidate_count") if latest_evaluation else None,
        "reviewed": latest_evaluation.get("reviewed_count") if latest_evaluation else None,
        "precisionAtK": latest_evaluation.get("precision_at_k") if latest_evaluation else None,
        "precisionAtKState": (
            "unknown"
            if not latest_evaluation or latest_evaluation.get("reviewed_count") is None
            else "insufficient-evidence"
            if latest_evaluation.get("reviewed_count") == 0
            else "known"
            if latest_evaluation.get("precision_at_k") is not None
            else "unknown"
        ),
    }

    latest_activity = _latest(rows, "MeaningfulActivity")
    latest_ingestion = _latest(rows, "Ingestion")
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


def _private_content(view: Mapping[str, Any], scan_error: str | None) -> str:
    needs = view["needsHaley"]
    residents = view["residents"]
    activity = view["recentActivity"]
    ingestions = view["recentIngestions"]
    intelligence = view["intelligenceSummary"]
    health = view["systemHealth"]

    warning = (
        '<div class="warning"><strong>Source refresh failed.</strong> Showing the last durable observations. '
        f'<span>{html.escape(scan_error)}</span></div>'
        if scan_error else ""
    )
    needs_html = "".join(
        f'<article><div>{_badge(row.get("state"))}<strong>{_text(row.get("display_name"), "Unnamed resident")}</strong></div>'
        f'<p>{_text(row.get("status_summary"), "No status summary")}</p>{_link(row.get("deepLink"), "Open repository")}</article>'
        for row in needs
    ) or _empty("No resident has reported a request for Haley.")
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
:root{{--ink:#16211d;--muted:#617069;--paper:#f4f2ea;--panel:#fffdf7;--line:#d9d6ca;--green:#296248;--amber:#976515;--red:#9b3f38;--blue:#335f7b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}header,main{{max-width:1240px;margin:auto}}header{{padding:38px 34px 22px;display:flex;justify-content:space-between;gap:24px;align-items:end}}h1{{font:700 34px/1.1 Georgia,serif;margin:4px 0}}h2{{font:700 23px/1.2 Georgia,serif;margin:0 0 16px}}.eyebrow,.meta,small{{color:var(--muted)}}nav{{display:flex;background:#e7e4da;border-radius:10px;padding:4px}}nav a{{padding:8px 13px;border-radius:7px;color:var(--ink);text-decoration:none}}nav a.active{{background:var(--panel);box-shadow:0 1px 3px #0002}}main{{padding:0 34px 54px}}section{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px;margin:0 0 18px}}.cards,.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}.cards article,.stack article,.metrics article{{border:1px solid var(--line);border-radius:10px;padding:14px}}article div{{display:flex;gap:8px;align-items:center}}article p{{margin:9px 0;color:var(--muted)}}.metrics article{{display:flex;flex-direction:column}}.metrics strong{{font:700 26px/1.2 Georgia,serif;margin-top:6px}}.stack{{display:grid;gap:10px}}.table{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}td small{{display:block}}a{{color:var(--blue)}}.badge{{display:inline-block;padding:2px 7px;border-radius:999px;background:#e3e5e2;color:#45514c;font-size:11px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}}.badge.known,.badge.fresh,.badge.active,.badge.complete,.badge.success{{background:#d9eadf;color:var(--green)}}.badge.partial,.badge.aging,.badge.needs-attention{{background:#f2e4c4;color:var(--amber)}}.badge.stale,.badge.attention,.badge.failed,.badge.error{{background:#f1d8d5;color:var(--red)}}.empty,.warning{{border:1px dashed var(--line);border-radius:10px;padding:18px;color:var(--muted)}}.warning{{border-style:solid;border-color:#d7b56d;background:#fff5dc;margin-bottom:18px}}.warning span{{display:block;font-size:12px;margin-top:4px}}@media(max-width:800px){{header{{align-items:start;flex-direction:column}}.cards,.metrics{{grid-template-columns:1fr 1fr}}}}@media(max-width:520px){{.cards,.metrics{{grid-template-columns:1fr}}header,main{{padding-left:18px;padding-right:18px}}}}
</style></head><body><header><div><div class="eyebrow">OPERATOR OVERVIEW · REAL OBSERVATIONS</div><h1>Command Center</h1><div class="meta">Generated {_text(view.get('generatedAt'), 'now')} · {_text(mode.title())} view</div></div><nav aria-label="Preview mode"><a class="{private_active}" href="/overview?view=private">Private</a><a class="{public_active}" href="/overview?view=public">Public preview</a></nav></header><main>{content}</main></body></html>"""
    return document.encode("utf-8")


def create_app(
    store: OperatorStore,
    *,
    workspace: Path,
    now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    scan_error: str | None = None,
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
        now = now_provider()
        records = _overview_records(store)
        view = (
            build_private_view(records, now=now, workspace=workspace)
            if mode == "private"
            else build_public_view(records, now=now)
        )
        if path == "/api/overview":
            body = json.dumps(view, separators=(",", ":"), sort_keys=True).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            body = render_page(view, mode=mode, scan_error=scan_error)
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
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Command Center only binds to a loopback host")

    store = OperatorStore(args.database)
    scan_error = None
    try:
        store.append_many(workspace_records(args.workspace), mode="real")
    except Exception as exc:  # noqa: BLE001 - preserve the last durable projection.
        scan_error = f"{type(exc).__name__}: {exc}"
    application = create_app(store, workspace=args.workspace, scan_error=scan_error)
    with make_server(args.host, args.port, application) as server:
        print(f"Command Center: http://{args.host}:{args.port}/overview?view=private")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
