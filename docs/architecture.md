# Architecture

WDW is a persistent computational environment whose state outlives any one UI,
agent run, or conversation. Its operating loop is:

`persistent world -> observe -> understand -> reconcile -> act -> learn -> continue`

The loop is a responsibility map, not a requirement that every iteration use an
LLM or take an external action.

1. **Persistent world** holds durable evidence, domain state, work, decisions,
   and action records.
2. **Observe** receives source events through connectors and persists them before
   acknowledging or routing them.
3. **Understand** derives bounded interpretations without rewriting evidence.
4. **Reconcile** compares desired and observed state using deterministic rules
   where possible.
5. **Act** requires explicit capability, policy, and an idempotency boundary.
6. **Learn** records outcomes and corrections without silently changing authority.
7. **Continue** schedules or reacts to the next observation.

The code is split by responsibility: `wdw_core` owns portable objects;
`wdw_inbox` durable ingress semantics; `wdw_connectors` transport translation;
`wdw_behavior` interpretations and proposals; `wdw_tools` effect authority;
`wdw_interfaces` replaceable projections; and `wdw_harness` loop composition.

At an ingress-to-change boundary, the responsibility chain is:

`outside world -> durable evidence / receipt -> communication + work routing -> bounded resident -> owning domain -> proposed / confirmed change`

A receipt establishes that something arrived; it is not a domain conclusion.
Communication and work records preserve coordination across retries and worker
replacement. Residents reason within a declared scope. The owning domain alone
accepts, rejects, or leaves a proposed change unresolved. No hop may turn an
unknown into a fact merely to keep the pipeline moving.

Places provide stable context for where a resident, interaction, or projection
is situated. They organize context; they do not replace domain ownership or make
a spatial rendering canonical.

**LLMs are components, not the architecture.**

**Deterministic where possible; agentic where valuable.**
