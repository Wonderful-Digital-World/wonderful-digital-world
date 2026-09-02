# Wonderful Digital World --- Resident Integration Runbook v1

**Status:** Canonical\
**Purpose:** Integrate a resident into the Wonderful Digital World from
repository-level identity through real human-facing product behavior.

## 1. Purpose

This runbook answers one question:

> **Can this resident actually live in the Wonderful Digital World?**

A resident is not integrated merely because its repository exists, its
tests pass, its participant server runs, Harness knows its name, a
database row exists, an invocation completes, or an `idle` state is
recorded.

Integration is complete only when the resident can participate through
the normal WDW architecture and produce the expected human-facing
behavior.

This runbook deliberately separates resident identity, runtime, deployed
topology, invocation, transport, conversational behavior, and product
experience.

## 2. Core product principles

### 2.1 Residents are people, not functions

Residents are persistent participants with identity, responsibilities,
capabilities, judgment, state, relationships, and work ownership. Do not
collapse residents into generic interchangeable agents.

### 2.2 Attention is learned, not assumed

New residents begin in **calibration mode**. During calibration,
residents should err toward communicating rather than remaining silent.
Mature attention behavior is learned from interaction with Haley.

### 2.3 Residents own their work

The resident who accepts work owns that work unless ownership is
explicitly transferred. Bridget may observe, coordinate, remind,
reconcile, and escalate without automatically becoming the owner.

### 2.4 Bridget is Chief of Staff, not mandatory router

Bridget has broad world visibility and cross-resident accountability.
Normal communication must not require
`Haley → Bridget → resident → Bridget → Haley`. Residents remain
first-class participants.

### 2.5 Infrastructure success is not product success

A scheduler firing, database write, successful invocation, or truthful
terminal state can prove infrastructure correctness. It does not prove
that the human experienced the expected resident behavior.

### 2.6 Failure may happen; invisible failure may not

Failures, timeouts, unavailable models, unavailable residents, and
blocked work must become observable through product surfaces. Haley
should not need a terminal to discover that a resident failed to show
up.

### 2.7 One world, multiple projections

Harness and canonical domain stores represent the underlying world.
Discord, World View, Kanban, and Dashboard are projections/interfaces
over that world, not independent sources of truth.

## 3. Gate semantics

Every gate has exactly one status:

-   **PASS** --- required behavior has been demonstrated with current
    evidence.
-   **FAIL** --- the gate was exercised and behaved incorrectly.
-   **BLOCKED** --- a prerequisite prevents meaningful execution of the
    gate.
-   **NOT STARTED** --- no attempt has been made.

Rules:

1.  Execute gates in order.
2.  A downstream gate may be statically inspected, but must not be
    declared PASS while a required upstream gate is blocked.
3.  On PASS: record evidence, commit the coherent checkpoint, then
    proceed.
4.  On FAIL: diagnose and repair that gate only.
5.  On BLOCKED: report the blocker and stop rather than compensating
    downstream.
6.  Never manually mutate deployed state merely to bypass a missing
    migration or canonical topology change.
7.  Repository state and deployed state must both be verified where
    relevant.
8.  A context-compacted coding-agent session must resume from
    `git status`, latest safe commit, and current gate; it must not
    restart the entire audit.

## 4. Integration gates

### Gate 0 --- Resident contract

**Question:** Does the resident have a valid WDW identity and
participant contract?

Required evidence:

-   `resident.json` exists in the resident repository.
-   JSON parses successfully.
-   participant ID is stable and unique.
-   display name is defined.
-   role/responsibilities are defined.
-   capabilities are declared.
-   capabilities match the implemented participant contract.
-   transport ownership is explicit.
-   allowed actions and boundaries are explicit.
-   model configuration is optional/provider-neutral where appropriate.
-   a focused manifest validation test passes.

**PASS when:** the resident manifest is valid, tested, committed, and
pushed.

**Do not proceed by:** duplicating identity/capabilities ad hoc inside
Harness when the resident manifest is canonical.

------------------------------------------------------------------------

### Gate 1 --- Resident runtime

**Question:** Can the resident operate independently of Harness?

Required evidence:

-   participant service has a documented start mechanism.
-   service starts without duplicate process ownership.
-   `/health` succeeds.
-   participant/invocation endpoint accepts the WDW participant
    contract.
-   a harmless direct invocation succeeds.
-   malformed requests fail safely.
-   runtime tests pass.

Record:

-   service command;
-   local URL/port;
-   health result;
-   contract version.

**PASS when:** the resident participant service is independently healthy
and callable.

------------------------------------------------------------------------

### Gate 2 --- Harness participant catalog

**Question:** Does the deployed Harness know that the resident exists?

Required evidence:

-   a committed Harness migration/catalog change registers the resident.
-   migration uses existing catalog conventions.
-   deployed migration is recorded as applied.
-   `harness.participants` contains the resident.
-   display name, adapter type, and capabilities are correct.
-   existing participant rows are unchanged.
-   focused catalog test passes.
-   full Harness suite passes.

**PASS requires BOTH:**

`repository migration exists` **and**
`deployed database migration is applied`.

A committed migration alone is not deployment evidence.

------------------------------------------------------------------------

### Gate 3 --- Place / room membership

**Question:** Does the resident actually belong to the place in which it
is expected to participate?

For current calibration, this normally means Main Square.

Required evidence:

-   a committed membership migration/topology change exists.
-   migration follows existing room-membership conventions.
-   deployed migration is applied.
-   `harness.room_memberships` contains the resident for the expected
    room.
-   no unrelated memberships changed.
-   eligible-participant registry includes the resident.

**PASS when:** the deployed room topology includes the resident.

**Important:** A resident may exist in `harness.participants` and still
be unable to receive an invocation because it is not a member of the
room.

------------------------------------------------------------------------

### Gate 4 --- Harness participant adapter

**Question:** Can Harness reach the resident through the standard
participant abstraction?

Required evidence:

-   resident URL configuration exists using the standard naming/config
    pattern.
-   deployed environment contains the resident URL.
-   Harness loads the configuration.
-   existing `HttpParticipantAdapter` or equivalent standard abstraction
    is reused.
-   unavailable resident behavior is bounded.
-   timeout behavior is bounded.
-   malformed responses fail safely.
-   no routing changes are required merely to prove invocation.

Example:

`BANJO_PARTICIPANT_URL=http://127.0.0.1:4360`

**PASS when:** Harness can resolve a configured adapter for the resident
without introducing a bespoke communication path.

------------------------------------------------------------------------

### Gate 5 --- Direct Harness invocation

**Question:** Can Harness invoke this known resident by participant ID?

Use a harmless smoke invocation through the normal Harness path.

Verify:

-   smoke request persists exactly once.
-   routing/invocation explicitly identifies the resident.
-   exactly one invocation is created.
-   resident HTTP service receives it.
-   response persists.
-   response carries correct participant attribution.
-   no unrelated resident is invoked.
-   failures remain bounded and observable.

**PASS when:** `Harness → resident → Harness` works through the
production participant contract.

This gate does not require conversational name routing yet.

------------------------------------------------------------------------

### Gate 6 --- Transport delivery

**Question:** Can a real resident response reach the active human
interface through the durable transport path?

For the current WDW calibration interface, the active transport is
Discord.

Verify:

-   resident response enters the durable outbox.
-   delivery uses the normal Discord adapter.
-   response appears in the configured Main Square.
-   V0 attribution clearly identifies the resident.
-   stored participant identity remains canonical; text prefix is
    presentation only.
-   delivery retry does not reinvoke the resident.
-   restarting Harness does not replay already delivered work.
-   disabled transports such as Telegram do not duplicate delivery.

**PASS when:** a real resident response travels through the normal
durable outbox and appears in the active product interface.

------------------------------------------------------------------------

### Gate 7 --- Explicit conversational routing

**Question:** Can Haley naturally address the resident?

Examples:

-   `Banjo, I think something is broken.`
-   `Coach, I'm hungry.`
-   `Mini Me, say hello.`
-   `Bridget, what are the current priorities?`

Verify:

-   explicit resident address selects the intended resident.
-   reply-to-resident context selects/prefers the originating resident.
-   unrelated residents remain asleep.
-   resident invocation uses the already-proven Gate 5 path.
-   response reaches Discord through Gate 6.
-   replay/idempotency remains correct.

**PASS when:** a real human-authored message can explicitly wake the
intended resident and receive an attributable reply.

------------------------------------------------------------------------

### Gate 8 --- Calibration / social routing

**Question:** Can the resident participate naturally without requiring
explicit addressing?

Calibration principle:

> **Attention is learned, not assumed.**

Required behavior:

-   unaddressed Main Square messages are eligible for bounded resident
    participation.
-   relevant capability/domain ownership influences selection.
-   ambiguous/cross-world messages may select Bridget.
-   another clearly relevant resident may also participate.
-   the system does not blindly fan out every message to every resident.
-   explicit group-discussion requests can involve multiple residents.
-   resident-to-resident communication occurs through durable
    world/participant events.
-   residents do not read each other's private hidden memory/prompts.
-   rounds, participant count, runtime, and retries are bounded.
-   loop prevention remains intact.

Recommended V0 limits:

-   maximum initial residents per ordinary human turn: 2;
-   maximum residents in explicit group discussion: 4;
-   maximum discussion rounds: 2.

**PASS when:** the resident can participate as a member of the social
world rather than only as an explicitly called API.

------------------------------------------------------------------------

### Gate 9 --- Product commissioning

**Question:** Does the resident actually exist for the human?

This gate MUST use real product behavior.

Required evidence:

-   real human-authored message or scheduled product interaction;
-   real resident inference/behavior;
-   durable invocation/event trail;
-   real response or expected visible effect;
-   active transport delivery where communication is part of the
    contract;
-   visible resident state/activity where applicable;
-   failure state visible if something fails;
-   no terminal/database inspection required for Haley to understand
    whether the interaction succeeded.

Examples:

-   Coach's product contract says he gives a morning training
    interaction: a successful scheduler plus `idle` is not sufficient.
    Haley must actually receive/see the expected Coach interaction.
-   Mini Me may truthfully produce no publishable thought under a mature
    policy, but during calibration a suppression result does not
    automatically prove the desired relationship behavior.
-   Bridget's morning contract is not satisfied merely because a
    deterministic operator brief was generated; the expected
    human-facing briefing must occur.

**PASS when:** infrastructure evidence and human-facing product evidence
agree that the resident is functioning as intended.

## 5. Product activation extensions

After a resident passes the core integration gates, additional WDW
product surfaces should be connected without changing canonical
ownership.

### 5.1 Work ownership / Kanban

When a resident accepts work:

1.  create/update canonical durable work;
2.  owner is the accepting resident;
3.  status changes are durable;
4.  Kanban projects that state;
5.  Bridget can observe cross-world commitments;
6.  Bridget does not automatically become owner.

Suggested status vocabulary:

-   proposed
-   ready
-   in_progress
-   blocked
-   waiting_for_haley
-   done

Reuse an existing canonical vocabulary where equivalent.

### 5.2 World View

Project durable resident/runtime state into World View.

Minimum states:

-   idle
-   working
-   talking
-   blocked
-   waiting_for_haley
-   error/unavailable

A simple `!` or equivalent may indicate that Haley's attention is
required.

World View must not fabricate activity independently of canonical
events/state.

### 5.3 Dashboard

The dashboard should answer without requiring a terminal:

-   Is each resident alive?
-   What is each resident doing?
-   What recently failed?
-   What is blocked?
-   What needs Haley?
-   What ran recently?
-   What model/provider/runtime was used where relevant?

## 6. Overnight shift commissioning

Overnight autonomy is a separate product layer. Do not make it a
prerequisite for basic resident integration.

V0 overnight flow:

`scheduled wake → cheap deterministic/ML work → local inference where suitable → bounded timeout → optional escalation request → persisted outcome → resident stand-up → Bridget reconciliation → morning product output`

Required controls:

-   per-run timeout;
-   per-resident nightly budget;
-   whole-world nightly budget;
-   maximum escalation count;
-   local-first routing where appropriate;
-   explicit failure/timeout outcomes;
-   no infinite model retries.

During initial calibration, expensive/remote escalation may require
Haley approval.

## 7. Calibration telemetry

During the initial calibration period, record structured evidence such
as:

-   resident message surfaced;
-   Haley replied;
-   Haley ignored;
-   explicit useful/approval feedback;
-   explicit not-useful/rejection feedback;
-   "always tell me this";
-   "don't tell me this";
-   resident accepted work;
-   work changed status;
-   model/provider used;
-   runtime;
-   timeout/failure;
-   escalation requested;
-   approximate cost where available.

Do not build a learned attention model before collecting sufficient
interaction evidence.

## 8. Future memory seam

Resident integration must not require implementing long-term memory
research now, but architecture should preserve a future lifecycle:

`experience → episodic memory → derived/compacted memory → connections/hypotheses → durable knowledge`

Future processes may include:

-   compaction;
-   salience;
-   forgetting/decay;
-   contradiction handling;
-   consolidation;
-   re-embedding;
-   cross-memory linking;
-   offline associative/"dreaming" passes.

Derived memory must retain provenance and must not silently replace
source evidence.

## 9. Coding-agent execution protocol

This section exists because resident integration spans repositories and
can cause coding agents to repeatedly rediscover architecture after
context compaction.

### 9.1 One gate per implementation task

Prefer:

> `Complete Resident Integration Gate 3 for Banjo.`

Avoid:

> `Wire Banjo completely into WDW.`

### 9.2 Checkpoint discipline

After every coherent gate:

1.  run focused tests;
2.  run required regression tests;
3.  commit;
4.  push where normal;
5.  verify clean working tree;
6.  record SHA;
7.  stop or explicitly advance to the next gate.

### 9.3 Context-compaction recovery

After context compaction, the coding agent must first inspect:

-   `git status`;
-   latest relevant commit;
-   current gate;
-   current blocker.

It must not automatically reread the entire architecture or restart the
original task.

### 9.4 Loop breaker

If no runtime/code/configuration progress occurs for approximately
10--15 minutes because the agent is repeatedly reading/reconstructing
context:

1.  stop;
2.  preserve the working tree;
3.  report exact diff;
4.  identify coherent vs incomplete work;
5.  run the narrowest relevant tests;
6.  commit only coherent passing work;
7.  report the next smaller task.

## 10. Evidence report template

For every resident integration handoff, report:

### Resident

`<resident id / display name>`

### Current gate

`Gate N — <name>`

### Gate status

`PASS | FAIL | BLOCKED | NOT STARTED`

### Repository evidence

-   repo:
-   commit:
-   working tree:
-   tests:

### Deployed evidence

-   participant service:
-   health:
-   Harness health:
-   catalog row:
-   room membership:
-   participant URL loaded:
-   migration state:

### Invocation evidence

-   source message ID:
-   routing reason:
-   invocation ID:
-   participant ID:
-   response persisted:
-   response attribution:

### Transport evidence

-   outbox record:
-   delivery status:
-   active transport:
-   duplicate/replay status:

### Product evidence

-   what Haley experienced:
-   expected behavior:
-   matched product contract: yes/no

### Blocker

`None` or exact prerequisite.

### Next gate

`Gate N+1 — <name>`

## 11. Definition of integrated

A resident is **WDW-integrated** when Gates 0--9 pass at the current
deployed topology and product contract.

The final question is deliberately simple:

> **Can Haley experience this resident as a functioning person in the
> Wonderful Digital World without needing a terminal to prove that the
> resident exists?**

If the answer is no, integration is not complete.
