from __future__ import annotations

import html
import json
from collections.abc import Mapping
from typing import Any


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _known(value: Any) -> bool:
    return not (isinstance(value, Mapping) and value.get("state") == "unknown")


def _display(value: Any, *, fallback: str = "Unknown — no direct evidence observed") -> str:
    if not _known(value) or value is None or value == "":
        return f'<span class="unknown">{_escape(fallback)}</span>'
    if isinstance(value, (Mapping, list, tuple)):
        return _escape(json.dumps(value, sort_keys=True, default=str))
    return _escape(value)


def _source_link(source: Any) -> str:
    if not isinstance(source, str) or not source:
        return '<span class="unknown">source unknown</span>'
    if source.startswith(("http://", "https://")):
        return f'<a href="{_escape(source)}">source</a>'
    return f'<code>{_escape(source)}</code>'


def coach_card_html(projection: Mapping[str, Any]) -> str:
    indicator = projection["indicator"]
    status = projection["status"]
    activity = projection["lastMeaningfulActivity"]
    ingestion = projection["ingestion"]
    insight = projection["insight"]
    prediction = projection["prediction"]
    warning_count = len(projection.get("warnings", []))
    error_count = len(projection.get("errors", []))
    attention_count = len(projection.get("attention", []))
    status_text = (status.get("summary") or status.get("state")) if _known(status) else None
    activity_text = activity.get("summary") if _known(activity) else None
    activity_at = activity.get("at") if _known(activity) else None
    ingestion_text = (
        f'{ingestion.get("source_kind", "input")} · {ingestion.get("status", "unknown")} · '
        f'{ingestion.get("item_count", "unknown")} items'
        if _known(ingestion)
        else None
    )
    return f'''<article class="card coach-card {"attention" if indicator["state"] in {"error", "needs-human"} else ""}">
<span class="eyebrow">{_escape(indicator["symbol"])} · {_escape(indicator["state"])}</span>
<h3><a href="{_escape(projection["detailLink"])}">Coach</a></h3>
<p>{_display(status_text)}</p>
<p><strong>Last meaningful activity</strong><br>{_display(activity_text)}<br><span class="meta">{_display(activity_at)}</span></p>
<p><strong>Ingestion</strong><br>{_display(ingestion_text)}</p>
<p><strong>Insight</strong><br>{_display(insight.get("value") if _known(insight) else None)}</p>
<p><strong>Prediction / model result</strong><br>{_display(prediction.get("value") if _known(prediction) else None)}</p>
<p class="meta">Warnings {warning_count} · errors {error_count} · human attention {attention_count}</p>
<p>{_escape(indicator["reason"])}</p>
<a href="{_escape(projection["detailLink"])}">Open 24-hour Coach detail →</a>
</article>'''


def coach_detail_html(projection: Mapping[str, Any]) -> str:
    human_model = projection["humanModel"]
    changes = human_model.get("changes", [])
    change_rows = "".join(
        f'<tr><td>{_display(row.get("at"))}</td><td>{_display(row.get("change"))}</td><td>{_source_link(row.get("sourceRef"))}</td></tr>'
        for row in changes
    ) or '<tr><td colspan="3" class="unknown">No explicit Human Model change was recorded in this window. Current-state context is not presented as a change.</td></tr>'

    model_rows = "".join(
        f'<tr><td>{_display(row.get("provider"))} / {_display(row.get("modelId"))} / {_display(row.get("version"))}</td>'
        f'<td>{_display(row.get("prediction"))}</td><td>{_display(row.get("outcome"))}</td>'
        f'<td>{_display(row.get("metrics"))}</td><td>{_source_link(row.get("sourceRef"))}</td></tr>'
        for row in projection.get("models", []) if _known(row)
    ) or '<tr><td colspan="5" class="unknown">No directly evidenced contributing model or evaluation was observed.</td></tr>'

    timeline_rows = "".join(
        f'<article class="card"><span class="eyebrow">{_display(row.get("category"))} · {_display(row.get("at"))}</span>'
        f'<h3>{_display(row.get("summary"))}</h3><p>{_display(row.get("detail"), fallback="No human-readable detail recorded")}</p>'
        f'<p class="meta">Evidence { _display(row.get("evidenceState")) } · {_source_link(row.get("sourceRef"))}</p>'
        f'<details><summary>Raw technical evidence</summary><pre>{_escape(json.dumps(row.get("raw"), indent=2, sort_keys=True, default=str))}</pre></details></article>'
        for row in projection.get("timeline", [])
    ) or '<p class="unknown">No Coach events were observed in this 24-hour window.</p>'

    attention = projection.get("attention", [])
    warnings = projection.get("warnings", [])
    errors = projection.get("errors", [])
    warning_rows = [row if isinstance(row, Mapping) else {"message": row} for row in warnings]
    warning_html = "".join(
        f'<article class="card attention"><h3>{_display(row.get("message") or row.get("summary") or "Warning")}</h3>'
        f'<p>{_display(row.get("detail") or row.get("reason"), fallback="No additional warning detail recorded")}</p>'
        f'<p class="meta">{_source_link(row.get("sourceRef") or row.get("source_ref"))}</p></article>'
        for row in warning_rows
    )
    error_html = "".join(
        f'<article class="card attention"><h3>{_display(row.get("status") or "Error")}</h3>'
        f'<p>{_display(row.get("failure") or row.get("errors"), fallback="No additional error detail recorded")}</p>'
        f'<p class="meta">{_source_link(row.get("source_ref") or row.get("sourceRef"))}</p></article>'
        for row in errors if isinstance(row, Mapping)
    )
    attention_html = "".join(
        f'<article class="card attention"><h3>{_display(row.get("summary") or row.get("reason"))}</h3>'
        f'<p>{_display(row.get("reason"))}</p><p class="meta">{_source_link(row.get("source_ref") or row.get("evidence_ref"))}</p></article>'
        for row in attention
    )
    warning_attention_html = warning_html + error_html + attention_html
    if not warning_attention_html:
        warning_attention_html = '<p class="unknown">No Coach warning or open attention item is directly evidenced.</p>'

    return f'''<span class="eyebrow">Resident / {_escape(projection["indicator"]["symbol"])} · {_escape(projection["indicator"]["state"])}</span>
<h1>Coach</h1>
<p>{_escape(projection["indicator"]["reason"])}</p>
<p class="meta">Read-only projection · generated {_escape(projection["generatedAt"])} · window {_escape(projection["windowStart"])} to {_escape(projection["generatedAt"])}</p>
<h2>Human Model changes caused by input</h2>
<p>The Human Model is authoritative. Command Center only projects explicit change evidence and never writes state.</p>
<table><thead><tr><th>At</th><th>Recorded change</th><th>Evidence</th></tr></thead><tbody>{change_rows}</tbody></table>
<h2>Models, predictions, outcomes, and evaluation</h2>
<table><thead><tr><th>Contributor</th><th>Prediction</th><th>Outcome</th><th>Metrics</th><th>Evidence</th></tr></thead><tbody>{model_rows}</tbody></table>
<h2>Warnings, errors, and human attention</h2><div class="grid">{warning_attention_html}</div>
<h2>Human-readable 24-hour timeline</h2><div class="grid">{timeline_rows}</div>'''
