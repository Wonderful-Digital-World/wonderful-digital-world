# Command Center operator guide

The Command Center is a private projection, not a source of truth. Resident
systems continue to own canonical state; adapters append evidence to the local
SQLite operator store. Meaningful activity and ingestion are distinct records,
and every timestamp is timezone-aware.

## Run locally

```sh
PYTHONPATH=packages python3 -m wdw_observability.launch
```

The launcher starts the Command Center and the separate `world-view` repository,
waits for both health surfaces, prints both URLs, and shuts both process groups
down together. Both servers refuse non-loopback hosts. Defaults are
`http://127.0.0.1:8787/overview` and `http://127.0.0.1:3000/rooms`.

The first run creates `wdw-command-center.sqlite3` and imports read-only evidence
from the sibling repositories. No synthetic records are inserted implicitly.
If a source or evaluation artifact is absent, the UI says so instead of
inventing a score. For fixture-only development, start the single server with:

```sh
PYTHONPATH=packages python3 -m wdw_observability --fixtures
```

The Overview contains exactly Bridget, Coach, Mini Me, and Banjo. The Human
Model is shown under models/data systems, not as a resident. Mini Me remains the
canonical owner of Thought Intelligence evaluation and review decisions; the
Command Center stores only a read-only projection/cache. A review control must
not be added until Mini Me exposes an explicit write boundary.

Set `WDW_THOUGHT_EVALUATION_ARTIFACT` to a Mini Me-owned JSON evaluation artifact
when one exists. Without one, the requested 72 thoughts, 360 candidates, and 0
reviewed are labelled unverified, while quality metrics, distributions, ranks,
reciprocal ranks, versions, readiness, and top candidates remain unavailable.
Similarity is displayed only as a retrieval signal, never as answer quality.

## Publish the safe Systems projection

The public export is a new object built from an explicit aggregate allowlist.
It is not a filtered copy of private JSON. The exporter rejects any projection
younger than the configured delay (24 hours by default), and the public-shape
guard rejects sensitive field names recursively.

```sh
PYTHONPATH=packages python3 -m wdw_observability.export_public \
  --workspace .. \
  --output ../haleyparks329.github.io/src/data/systems.json
```

Do not reduce the release delay for a production export. Sensitive fixture
detection and projection tests are release blockers.

## Airtable boundary

No safe, existing Airtable integration was found during the audit, so this
implementation intentionally does not add one. If a temporary proof of concept
is useful, export only the public projection fields or private aggregate fields
approved for that base. Airtable remains a disposable operational view and must
never become canonical storage or receive raw resident payloads, notes, URLs,
identifiers, or activity logs.
