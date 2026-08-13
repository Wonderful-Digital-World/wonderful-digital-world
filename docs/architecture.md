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

**LLMs are components, not the architecture.**

**Deterministic where possible; agentic where valuable.**
