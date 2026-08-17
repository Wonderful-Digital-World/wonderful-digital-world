from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import URLError
from urllib.parse import quote, unquote
from urllib.request import urlopen
from wsgiref.simple_server import make_server

from .projections import private_overview
from .refresh import ProjectionRefresher
from .sample import synthetic_records
from .store import OperatorStore


StartResponse = Callable[[str, list[tuple[str, str]]], object]


def _escape(value: object) -> str:
    return html.escape(str(value))


def _value(value: object, fallback: str = "Unavailable") -> str:
    return _escape(fallback if value is None or value == "" else value)


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{_escape(title)} · WDW Command Center</title><style>
:root{{color-scheme:dark;font:16px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#111310;color:#e8e5dc}}*{{box-sizing:border-box}}body{{margin:0}}a{{color:#b9cfac}}header,main{{width:min(1120px,92vw);margin:auto}}header{{display:flex;align-items:center;gap:2rem;padding:1.2rem 0;border-bottom:1px solid #353a32}}header strong{{margin-right:auto}}nav a{{margin-left:1.1rem}}main{{padding:3rem 0 5rem}}h1{{font:500 clamp(2rem,5vw,4.3rem)/1.05 Georgia,serif;max-width:18ch}}h2{{margin-top:3rem;font-size:.78rem;text-transform:uppercase;letter-spacing:.14em;color:#a4aa9d}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem;margin:1.2rem 0}}.card{{border:1px solid #353a32;background:#171a16;padding:1.1rem;min-height:9rem}}.card p{{color:#b8bcb3}}.eyebrow,.meta{{color:#8e9688;font-size:.78rem;text-transform:uppercase;letter-spacing:.1em}}.attention{{border-color:#a9755c}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;vertical-align:top;padding:.75rem .4rem;border-bottom:1px solid #353a32}}.unknown{{color:#d8b589}}iframe{{width:100%;min-height:68vh;border:1px solid #353a32;background:white}}code{{overflow-wrap:anywhere}}
</style></head><body><header><strong>WDW / private</strong><nav><a href="/overview">Overview</a><a href="/world">World</a><a href="/models">Models</a></nav></header><main>{body}</main></body></html>""".encode()


def _overview_body(view: dict[str, object]) -> str:
    residents = view["residents"]
    needs = view["needsHaley"]
    cards = "".join(
        f'<article class="card {"attention" if row["state"] == "needs-attention" else ""}"><span class="eyebrow">{_escape(row["state"])} · evidence {_escape(row["evidence_state"])}</span><h3><a href="/residents/{quote(row["resident_id"])}">{_escape(row["display_name"])}</a></h3><p>{_escape(row["status_summary"])}</p><p class="meta">Source time: {_value(row.get("occurred_at"))}</p></article>'
        for row in residents
    ) or '<p class="unknown">No resident evidence observed.</p>'
    needs_cards = "".join(
        f'<article class="card attention"><span class="eyebrow">{_escape(row.get("category", "attention"))} · owner {_value(row.get("owner"))}</span><h3>{_escape(row.get("summary", "Attention required"))}</h3><p>{_escape(row.get("reason", ""))}</p><p class="meta">Resident: <a href="/residents/{quote(str(row.get("resident_id", "")))}">{_escape(row.get("resident_id", "unknown"))}</a> · evidence {_value(row.get("evidence_ref"))} · source {_value(row.get("source_ref"))} · work item {_value(row.get("related_work_item_id"))}</p></article>'
        for row in needs
    ) or '<p class="unknown">No open attention item is currently evidenced for Haley.</p>'
    activity = "".join(f'<tr><td>{_escape(row["resident_id"])}</td><td>{_escape(row["summary"])}</td><td>{_escape(row["occurred_at"])}</td></tr>' for row in view["recentActivity"]) or '<tr><td colspan="3" class="unknown">No meaningful activity observed.</td></tr>'
    ingestions = "".join(f'<tr><td>{_escape(row["resident_id"])}</td><td>{_escape(row["source_kind"])}</td><td>{_value(row.get("item_count"))}</td><td>{_escape(row["status"])}</td></tr>' for row in view["recentIngestions"]) or '<tr><td colspan="4" class="unknown">No ingestion evidence observed.</td></tr>'
    projection = view.get("projection", {})
    return f'<span class="eyebrow">Operator projection</span><h1>The world, at useful resolution.</h1><p class="meta">Generated {_escape(view["generatedAt"])} · refresh {_value(projection.get("state") if isinstance(projection, dict) else None, "static")} · last success {_value(projection.get("lastSuccessAt") if isinstance(projection, dict) else None, "Unavailable")} · error {_value(projection.get("error") if isinstance(projection, dict) else None, "none")}</p><h2>Residents · {len(residents)}</h2><div class="grid">{cards}</div><h2>Needs Haley · {len(needs)}</h2><div class="grid">{needs_cards}</div><h2>Recent meaningful activity</h2><table><thead><tr><th>Resident</th><th>Outcome</th><th>Occurred</th></tr></thead><tbody>{activity}</tbody></table><h2>Recent ingestions</h2><table><thead><tr><th>Resident</th><th>Source</th><th>Items</th><th>Status</th></tr></thead><tbody>{ingestions}</tbody></table>'


def _json_detail(value: object) -> str:
    if not value:
        return '<span class="unknown">Unavailable</span>'
    return f'<code>{_escape(json.dumps(value, sort_keys=True))}</code>'


def _models_body(records: Iterable[dict[str, object]]) -> str:
    rows = list(records)
    versions = [row for row in rows if row.get("kind") == "ModelVersion"]
    evaluations = [row for row in rows if row.get("kind") == "EvaluationRun"]
    registry = "".join(
        f'''<article class="card"><span class="eyebrow">{_escape(row.get("model_id", "unknown"))} / {_value(row.get("version"))}</span><h3>{_value(row.get("summary"), "Observed model artifact")}</h3><p>Readiness: {_value(row.get("readiness"), "Unknown")} · evidence: {_value(row.get("evidence_state"), "unknown")}</p><p class="meta">Observed from source time {_value(row.get("occurred_at"))}</p></article>'''
        for row in versions
    ) or '<p class="unknown">No model-version artifact observed.</p>'
    cards = []
    for row in evaluations:
        raw_reviewed = row.get("reviewed_count")
        reviewed = int(raw_reviewed) if raw_reviewed is not None else None
        pk = "Unknown — evaluation evidence unavailable" if reviewed is None else ("Unavailable — no reviewed labels" if reviewed == 0 else _value(row.get("precision_at_k"), "Unknown"))
        top = _json_detail(row.get("top_candidates"))
        cards.append(f'''<article class="card"><span class="eyebrow">{_escape(row.get("model_id", "unknown"))} / {_value(row.get("model_version"))}</span><h3>{_value(row.get("thought_count"))} thoughts · {_value(row.get("candidate_count"))} candidates</h3><p>Reviewed: {_value(reviewed)} · evidence: {_escape(row.get("evidence_state", "unknown"))}</p><table><tbody><tr><th>Similarity</th><td>mean {_value(row.get("mean_similarity"))} · median {_value(row.get("median_similarity"))} · range {_value(row.get("min_similarity"))}–{_value(row.get("max_similarity"))}</td></tr><tr><th>P@1 / P@3 / P@5</th><td class="unknown">{pk}</td></tr><tr><th>Distribution</th><td>{_json_detail(row.get("score_distribution"))}</td></tr><tr><th>Rank behavior</th><td>{_json_detail(row.get("rank_behavior"))}</td></tr><tr><th>Reciprocal graph</th><td>{_json_detail(row.get("reciprocal_graph"))}</td></tr><tr><th>Analysis version</th><td>{_value(row.get("analysis_version"))}</td></tr><tr><th>Readiness</th><td>{_value(row.get("readiness"), "Unknown")}</td></tr><tr><th>Top candidates</th><td>{top}</td></tr><tr><th>Ownership</th><td>{_value(row.get("canonical_owner"))} is canonical; Command Center projection is {_escape("read-only" if row.get("read_only", True) else "writable")}</td></tr></tbody></table><p class="unknown">Similarity is a candidate-generation signal, not a quality judgment. Precision is unavailable until labels exist.</p></article>''')
    return '<span class="eyebrow">Models and evaluations</span><h1>Intelligence, with the uncertainty intact.</h1><h2>Model registry</h2><div class="grid">' + registry + '</div><h2>Evaluation history</h2><div class="grid">' + ("".join(cards) or '<p class="unknown">Unavailable — no evaluation artifact observed.</p>') + '</div>'


def _resident_body(resident_id: str, records: list[dict[str, object]]) -> str | None:
    snapshot = next((row for row in records if row["kind"] == "ResidentSnapshot" and row.get("resident_id") == resident_id), None)
    if not snapshot:
        return None
    history = [row for row in records if row.get("resident_id") == resident_id and row["kind"] != "ResidentSnapshot"]
    rows = "".join(f'<tr><td>{_escape(row["kind"])}</td><td>{_escape(row.get("summary") or row.get("status") or "Observed")}</td><td>{_escape(row["evidence_state"])}</td><td>{_escape(row["occurred_at"])}</td></tr>' for row in history) or '<tr><td colspan="4" class="unknown">No resident history observed.</td></tr>'
    return f'<span class="eyebrow">Resident / {_escape(snapshot["state"])} · evidence {_escape(snapshot["evidence_state"])}</span><h1>{_escape(snapshot["display_name"])}</h1><p>{_escape(snapshot["status_summary"])}</p><p class="meta">Last meaningful activity: {_value(snapshot.get("last_meaningful_activity_at"), "Unknown")}</p><h2>Observed history</h2><table><thead><tr><th>Kind</th><th>Summary</th><th>Evidence</th><th>Occurred</th></tr></thead><tbody>{rows}</tbody></table>'


def _is_online(url: str) -> bool:
    try:
        with urlopen(url, timeout=.6) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def create_app(store: OperatorStore | None = None, *, mode: str = "real", world_url: str | None = None, world_health_url: str | None = None, refresher: ProjectionRefresher | None = None):
    operator_store = store or OperatorStore(Path(os.environ.get("WDW_COMMAND_CENTER_DB", "wdw-command-center.sqlite3")))
    configured_world = world_url or os.environ.get("WDW_WORLD_VIEW_URL", "http://127.0.0.1:3000/rooms")
    health_url = world_health_url or configured_world.removesuffix("/rooms") + "/"

    def application(environ: dict[str, object], start_response: StartResponse):
        path = unquote(str(environ.get("PATH_INFO", "/"))).rstrip("/") or "/"
        if path == "/":
            start_response("302 Found", [("Location", "/overview"), ("Content-Length", "0")]); return [b""]
        if path == "/healthz":
            payload = b'{"status":"ok"}'; start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))]); return [payload]
        if refresher is not None:
            refresher.refresh()
        records = operator_store.records(limit=1000, mode=mode)
        overview = private_overview(records, datetime.now(timezone.utc))
        overview["projection"] = refresher.status() if refresher else {
            "state": "static", "lastAttemptAt": None, "lastSuccessAt": None,
            "error": None, "intervalSeconds": None,
        }
        if path == "/api/overview":
            payload = json.dumps(overview, separators=(",", ":")).encode(); start_response("200 OK", [("Content-Type", "application/json"), ("Cache-Control", "no-store"), ("Content-Length", str(len(payload)))]); return [payload]
        if path == "/overview": payload = _page("Overview", _overview_body(overview))
        elif path == "/models": payload = _page("Models", _models_body(records))
        elif path == "/world":
            body = f'<span class="eyebrow">Existing World View projection</span><h1>Move through the world.</h1><iframe title="World View" src="{_escape(configured_world)}"></iframe>' if _is_online(health_url) else '<span class="eyebrow">World View / offline</span><h1>The world is not running.</h1><article class="card"><p class="unknown">World View did not answer its local health check. The Command Center remains available.</p><p>Start both services with <code>wdw-start</code>. This route never executes arbitrary shell commands.</p></article>'
            payload = _page("World", body)
        elif path.startswith("/residents/"):
            body = _resident_body(path.removeprefix("/residents/"), records)
            if body is None:
                payload = _page("Not found", "<h1>Resident not observed.</h1>"); start_response("404 Not Found", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(payload)))]); return [payload]
            payload = _page("Resident", body)
        else:
            payload = _page("Not found", "<h1>Nothing observed here.</h1>"); start_response("404 Not Found", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(payload)))]); return [payload]
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store"), ("Content-Length", str(len(payload)))]); return [payload]
    return application


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the private WDW Command Center.")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("WDW_COMMAND_CENTER_DB", "wdw-command-center.sqlite3")))
    parser.add_argument("--host", default=os.environ.get("WDW_COMMAND_CENTER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WDW_COMMAND_CENTER_PORT", "8787")))
    parser.add_argument("--fixtures", action="store_true", help="Use isolated synthetic fixtures instead of real adapters.")
    parser.add_argument("--refresh-seconds", type=float, default=float(os.environ.get("WDW_COMMAND_CENTER_REFRESH_SECONDS", "5")))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}: raise SystemExit("Command Center is private; use a loopback host.")
    if args.refresh_seconds <= 0: raise SystemExit("--refresh-seconds must be positive")
    store = OperatorStore(args.database)
    if args.fixtures:
        mode = "fixture"
        store.reconcile(synthetic_records(), mode=mode)
        refresher = None
    else:
        mode = "real"
        store.purge_fixtures()
        refresher = ProjectionRefresher(store, args.workspace, interval_seconds=args.refresh_seconds)
        refresher.refresh(force=True)
    with make_server(args.host, args.port, create_app(store, mode=mode, refresher=refresher)) as server:
        print(f"WDW Command Center: http://{args.host}:{args.port}/overview")
        server.serve_forever()


if __name__ == "__main__":
    main()
