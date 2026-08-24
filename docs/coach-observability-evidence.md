# Coach observability commissioning evidence

Date: 2026-08-24

## Scope

This commissioning is intentionally limited to Coach. The Coach resident card and
24-hour detail view are read-only projections over existing WDW observability
records. They do not establish a generic resident protocol or create a second
source of truth.

The projection reuses:

- resident snapshots, meaningful activity, ingestion, attention, model versions,
  and evaluation runs from the Command Center store;
- morning insight operations from the agent-harness activity log; and
- explicit Human Model changes carried by those records.

The Human Model remains authoritative. Current-state context read by Coach is not
reported as a Human Model change. A change appears only when the source record
explicitly names a `human_model_change` or `human_model_changes` field (including
camel-case equivalents).

## Acceptance-flow evidence

### A. A new message reaches Coach

Automated commissioning coverage writes a fresh `MeaningfulActivity` with
`activity_kind=received-input`, then verifies that it appears as a human-readable
input in the Coach timeline. A same-process refresh test appends another activity
after the Command Center has started and verifies that the second request sees it
without a restart.

There was no shared live `.wdw/resident-activity-v1.jsonl` file in the inspected
workspace on 2026-08-24, so a live message-flow claim cannot yet be made.

### B. A new MacroFactor datum reaches Coach

Automated commissioning coverage records a Coach `Ingestion` whose source kind is
`MacroFactor`, and verifies both the resident-card ingestion state and the
`input-and-ingestion` timeline entry.

The inspected persisted WDW store did not contain a live Coach MacroFactor
ingestion record, so the end-to-end live connector remains unproved here.

### C. Repaired morning-insight path

Automated commissioning coverage records a completed morning operation with
current-state context, an explicit Human Model change, model and prediction
metadata, an insight, and delivered output. It verifies every corresponding
timeline category plus the contributing model's evaluation metrics.

The persisted agent-harness log provides partial live evidence:

- an older end-to-end occurrence delivered a morning insight on 2026-08-21;
- the 2026-08-24 recovery attempts read canonical planned-training context,
  including `trainingSchedule`, `activeTrainingBlock`, `trainingFrequency`, and
  `nutritionPhase`; and
- the current recovery occurrence remains incomplete with
  `morning_insight_extension_missing`.

Those facts are deliberately not combined into a false successful-recovery
claim. The detail view exposes the current incomplete operation as an error. A
new completed occurrence is still required to prove that the repaired live path
both reads planned training and produces the canonical final insight.

## State and failure behavior

- `…` is backed by a recent working snapshot or pending/running/incomplete morning
  operation.
- `!` is backed by a recent insight or delivery result.
- `?` is backed by an open human-attention item.
- `error` is backed by a failure, failed/error status, or ingestion errors.
- `idle` means none of those conditions has direct evidence in the 24-hour window.
- Unknown card fields are rendered as unknown rather than inferred.

Malformed shared activity lines are isolated into an attention item, so one bad
record does not prevent the Command Center from refreshing other residents or
later valid Coach records.

## Verification

The commissioning tests are in `tests/test_command_center_overview.py` and
`tests/test_resident_activity.py`. Run them with:

```sh
PYENV_VERSION=3.12.8 python -m pytest \
  tests/test_command_center_overview.py tests/test_resident_activity.py
```

The complete repository suite should also be run before release.

## Remaining gaps

- Capture live flow-A and flow-B records from their real producers.
- Repair `morning_insight_extension_missing`, then capture one new completed live
  flow-C occurrence with canonical planned-training input and final delivery.
- Emit explicit Human Model change evidence when the authoritative Human Model
  actually persists a change; context reads alone are insufficient.
- Persist model-version and evaluation records for live Coach runs if production
  metrics are expected in the detail view.
- Apply this pattern to another resident only after defining that resident's own
  evidence and authority boundaries.
