# Four-resident coexistence — Runbook v1 remediation status

Date assessed: 2026-08-28
Final status: **PARTIAL — blockers repaired; natural exact-revision confirmation pending**

## Resident status

| Resident | Exact installed revision | Status |
|---|---|---|
| Mini Me | `fc66b2341f605d21a0297efd2f3a769c19a422cc` | **COMMISSIONED** — Gates 0–9 PASS after the natural 07:00 run. Its lack of a Telegram message was truthful suppressed/idle behavior. |
| Bridget | `e3abb8536e4644c47950b369cfd044c00147bfd6` | **NOT COMMISSIONED** — terminal-activity repair installed; Gate 0 PASS, Gates 1–8 pending a natural run at this exact revision, Gate 9 BLOCKED. |
| Banjo | `5e666c5a7c1b5a39aab94f3859770e41f89964ee` | Unchanged; previously commissioned evidence retained. |
| Coach | `a0bc6786ebf8df615879deed836ba1a296010bcb` | Resident revision unchanged; duplicate-schedule and stale-retry remediation installed in Agent Harness `000f83b3575ea03191a4e650b6cee4883283f592`; clean natural confirmation pending. |

Banjo was not rerun. Neither Bridget nor Coach was manually triggered, and the full four-resident matrix was not rerun.

## Repairs

### Bridget terminal observability

Bridget now emits `working` and exactly one truthful terminal activity: `idle` for successful, idempotent, or deliberately suppressed outcomes, and `error` for failures. The activity uses one execution identity throughout the run. The repaired exact revision is installed in `com.haleyparks.bridget-morning-operations` with the 09:00 Europe/Copenhagen schedule and `RunAtLoad=false`.

The 2026-08-28 09:00 natural run exposed the defect at the former installed revision `98f8290e9b6f49dd84caf5558b2c80b17a00cbc5`. That evidence remains valid as defect evidence but cannot commission the repaired revision.

### Coach duplicate prevention

The duplicate messages were consistent with two enabled 06:30 producers: standalone Coach and the Agent Harness durable task `daily_coach_morning_briefing`. Agent Harness now retires that redundant durable task while retaining its audit record. The live task is disabled, and standalone `com.haleyparks.coach.morning` is the sole scheduled 06:30 producer.

Agent Harness also bounds delivery attempts at three, expires an older local-date occurrence, records `expired` or `retry_exhausted`, and refuses delivery of a prior-local-day Coach occurrence. Migration 014 was applied successfully. All five Harness LaunchAgents are installed at `000f83b3575ea03191a4e650b6cee4883283f592` and passed their health checks.

## Targeted coexistence assertions

The prior natural evidence established three assertions and exposed two blockers. The implementations and installed configuration are repaired, but assertions that depend on runtime uniqueness cannot be promoted until the next natural occurrences.

| Assertion | Status | Evidence treatment |
|---|---|---|
| Canonical persistence ownership | **PASS** | Retained exact-revision-valid evidence; Mini Me's new natural run is consistent. |
| Resident-correct terminal attribution | **PENDING NATURAL** | Bridget repair installed; requires its next natural exact-revision run. |
| Suppressed/idle isolation | **PASS** | Mini Me's natural run produced one resident-correct suppressed/idle terminal activity and no delivery. |
| Retry/idempotency isolation | **PENDING NATURAL** | Coach duplicate source removed and retries bounded; requires the next natural 06:30 occurrence to prove one output. |
| Absence of cross-resident leakage | **PASS** | Retained evidence plus Mini Me's resident-consistent identifiers and persistence. |

Overall coexistence status remains **PARTIAL**. Persistence ownership is PASS; terminal observability and retry/idempotency cannot yet be promoted to PASS as a complete four-resident result.

## Retained coexistence evidence

Existing PASS evidence remains reused for routing, canonical persistence, suppressed/idle isolation, failure isolation, unaffected delivery identity, shared services, and absence of cross-resident leakage. No new evidence invalidated Banjo or the retained Mini Me evidence. Schedule-separation and no-duplicate claims for Coach require new natural proof after the repair.

## Evidence classification

- **New:** Mini Me's natural 2026-08-28 07:00 execution; Bridget's natural 09:00 defect evidence; the user-provided Coach duplicate evidence and producer correlation; both repair commits, tests, installations, migration result, live schedule state, and health checks.
- **Reused:** exact-revision-valid Mini Me and Banjo evidence; routing, canonical-persistence, suppression, failure-isolation, unaffected delivery-identity, shared-service, and leakage evidence; Coach resident evidence unaffected by its unchanged revision.
- **Invalidated for current closure:** Bridget's former-revision natural run as proof of the repaired revision; prior Coach schedule-separation and no-duplicate conclusions. These remain historical evidence of the defects.

## Tests and installation checks

- Mini Me: build PASS; 55 tests PASS; natural exact-revision run PASS.
- Bridget: 464 tests PASS, 10 skipped, one existing warning; repaired LaunchAgent installed and idle without a manual trigger.
- Agent Harness: 240/240 tests PASS; build PASS; generated-artifact diff check PASS.
- Agent Harness migration 014 PASS; redundant durable Coach task confirmed disabled.
- Harness health checks PASS at the exact installed revision; standalone Coach remains scheduled, idle, and last exited successfully.

## Exact revisions

- Mini Me: `fc66b2341f605d21a0297efd2f3a769c19a422cc`
- Bridget: `e3abb8536e4644c47950b369cfd044c00147bfd6`
- Banjo: `5e666c5a7c1b5a39aab94f3859770e41f89964ee`
- Coach: `a0bc6786ebf8df615879deed836ba1a296010bcb`
- Agent Harness: `000f83b3575ea03191a4e650b6cee4883283f592`
- Wonderful Digital World evidence baseline before the closure-document commit: `cfb4d1a1037b0a7dfeb386269e3f84493d4724c9`

## Documentation and commit state

The Bridget and Agent Harness runtime repairs are committed in their respective repositories. At the user's direction, the commissioning reports are committed and published for handoff. These later documentation commits advance repository `HEAD` but do not change installed executables or replace the explicit installed exact revisions above. A fresh upstream comparison found no remote divergence, and no force update was used.

## Remaining natural-evidence blockers

- Coach: inspect the natural 06:30 Europe/Copenhagen occurrence from 2026-08-29 and prove one appropriate output with no duplicate or stale retry.
- Bridget: inspect the natural 09:00 Europe/Copenhagen occurrence from 2026-08-29 at `e3abb8536e4644c47950b369cfd044c00147bfd6` and complete Gates 1–8, then Gate 9 if valid.

The known implementation blockers are fixed, but these evidence prerequisites mean all four residents cannot yet be declared commissioned and coexistence cannot yet be declared PASS.
