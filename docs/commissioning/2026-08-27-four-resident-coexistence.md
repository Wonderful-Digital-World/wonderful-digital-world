# Targeted Resident Repair and Coexistence Follow-up — 2026-08-27

## Outcome

The bounded Bridget and Mini Me repairs are implemented, tested, installed, and
exact-revision pinned. Neither resident can yet be declared commissioned:
Bridget still requires a new natural 09:00 occurrence, and Mini Me still
requires a new natural 07:00 occurrence. Those schedule times had already
passed before the repairs were installed, and manual execution is not a
substitute for natural-schedule evidence.

Banjo and Coach remain commissioned. Their launch definitions and shared
runtime isolation were inspected but their Gates 0–9 were not rerun because the
repairs did not alter their code, schedules, state namespaces, or launch jobs.

## Authority and Scope

- Authority: Resident Commissioning Runbook v1 and the evidence from the
  original four-resident commissioning pass.
- Scope: repair only Bridget's exact-revision launcher boundary and Mini Me's
  canonical state and terminal-activity boundary.
- Stop rule: do not manufacture natural evidence and do not expand into a full
  four-resident recommissioning unless shared infrastructure is affected.
- Evidence is classified below as invalidated, new, or reused.

## Repair Summary

| Resident | Repair | Installed revision | Current result |
|---|---|---|---|
| Bridget | Replaced the stale pin with a canonical-exec launcher bound to the production-intended checkout and canonical WDW paths | `98f8290e9b6f49dd84caf5558b2c80b17a00cbc5` | Gate 0 static boundary repaired; BLOCKED on next natural 09:00 occurrence |
| Mini Me | Converged on one canonical state path, migrated the newer legacy state with backup, emitted exactly one terminal activity result for every outcome, and replaced the stale loaded job | `fc66b2341f605d21a0297efd2f3a769c19a422cc` | Gates 0 and 8 repaired in static/manual evidence; BLOCKED on next natural 07:00 occurrence |
| Banjo | No change | `5e666c5a…` remains loaded | COMMISSIONED; not rerun |
| Coach | No change | `a0bc678…` remains loaded | COMMISSIONED; not rerun |

The detailed before/after evidence and gate reasoning are in the Bridget and
Mini Me resident reports.

## Targeted Coexistence Check

| Invariant | Result | Evidence |
|---|---|---|
| Runtime isolation | PASS | All four loaded jobs retain distinct canonical repositories, work directories, schedules, and resident state namespaces. |
| Persistence isolation | PASS for repaired configuration | Mini Me now reads and writes only `WDWRuntimeState/mini-me/thought-daily.json`; the legacy path is migration input only. Bridget, Banjo, and Coach namespaces were unchanged. |
| Schedule separation | PASS | Banjo remains 02:00, Coach 06:30, Mini Me 07:00, and Bridget 09:00 local. |
| Failure isolation | PASS | Reloading Bridget and Mini Me did not modify or stop the loaded Banjo and Coach jobs. |
| Delivery identity | REUSED | No delivery-routing behavior changed. The original exact-revision-valid evidence for Banjo, Coach, and Mini Me's suppressed user effect is retained; no new user-visible delivery was triggered. |
| Observability | PASS for repair acceptance; BLOCKED for natural proof | Mini Me's manual duplicate occurrence produced exactly one correlated idle terminal event. Bridget and Mini Me still require natural post-repair terminal evidence. |
| Retry and idempotency | PASS in tests/manual repair check | Mini Me's normal, suppressed, duplicate/no-op, and failure paths each produce exactly one distinct terminal result; the manual duplicate run produced no user delivery. |
| Shared infrastructure impact | PASS | Banjo and Coach remain loaded with their prior exact pins, canonical paths, successful last exits, and unchanged schedules. |

Targeted coexistence is **repaired but awaiting natural confirmation**. No
cross-resident collision or shared-infrastructure regression was found.

## Evidence Classification

### Invalidated

- Bridget's original Gate 0 evidence and all downstream non-results tied to the
  stale `848561e…` installed pin.
- Mini Me's original Gate 0 claim because the loaded job did not match the
  on-disk canonical-exec plist.
- Mini Me's original Gate 8 evidence because the active state source was legacy
  and the suppressed occurrence lacked terminal shared activity.

### New

- Bridget installer/template validation, exact pin `98f8290e…`, loaded/on-disk
  agreement, canonical paths, and the 461-test safe suite.
- Mini Me canonical-only state implementation, explicit state migration and
  backup, exact pin `fc66b234…`, loaded/on-disk agreement, 55-test safe suite,
  and one-terminal-event manual duplicate evidence.
- Read-only confirmation that Banjo and Coach remain isolated and successfully
  loaded at their prior pins.

### Reused

- Bridget exact-revision-valid static dependency, effect, and safety evidence;
  it does not satisfy the missing natural occurrence.
- Mini Me Gates 1–7 evidence that is independent of the invalidated launcher
  and persistence assumptions; it does not satisfy the missing natural
  occurrence.
- Banjo and Coach Gates 0–9 and delivery/routing evidence, because neither
  resident nor its shared dependencies changed.

## Validation

- Bridget: `461 passed, 10 skipped, 26 subtests passed`.
- Mini Me: build passed; `55 tests, 55 passed`.
- Mini Me's tests cover the canonical path, rejection of the legacy variable as
  source of truth, normal terminal completion, suppressed completion, duplicate
  no-op completion, distinct failure completion, and no duplicate terminal.
- Installed plist and loaded-job inspection agree for both repaired residents.

## Changes and Commits

- Bridget: `98f8290e9b6f49dd84caf5558b2c80b17a00cbc5` — `Pin Bridget morning job to canonical revision`.
- Mini Me: `fc66b2341f605d21a0297efd2f3a769c19a422cc` — `Repair Mini-Me daily state and terminal activity`.
- Resident reports remain outside those runtime commits so the installed exact
  pins are not shifted by documentation-only commits.
- Runbook v1 was not modified. Proposed v1.1 clarifications were appended to
  the framework lessons document.

## Remaining Natural Evidence

1. Observe Mini Me's next natural 07:00 occurrence and require canonical state
   plus exactly one correlated terminal activity event.
2. Observe Bridget's next natural 09:00 occurrence and map its persisted work,
   effect, state, and terminal activity through Gates 0–9.
3. Update the two resident reports and this follow-up with those results. Do not
   replace either occurrence with a manual run.

## Current Status

- Bridget: **BLOCKED — awaiting next natural 09:00 occurrence**.
- Mini Me: **BLOCKED — awaiting next natural 07:00 occurrence**.
- Banjo: **COMMISSIONED — prior Gates 0–9 retained**.
- Coach: **COMMISSIONED — prior Gates 0–9 retained**.
- Targeted coexistence: **REPAIRED, NATURAL CONFIRMATION PENDING**.
