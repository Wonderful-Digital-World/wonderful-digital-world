# Implementation status

Every material claim uses one of these labels:

- **implemented** — executable here and covered by a test or example;
- **dogfood-ready** — integrated enough for private real-world evaluation;
- **experimental** — working exploration without a stable contract;
- **planned** — accepted design with no implementation yet;
- **aspirational** — direction, not a delivery commitment;
- **intentionally rejected** — considered and excluded from the architecture.

| Capability | Status | Evidence or limit |
| --- | --- | --- |
| Portable objects and status vocabulary | implemented | `wdw_core`, contract tests |
| Idempotent persist-before-route semantics | implemented | in-memory `wdw_inbox`; process durability not claimed |
| Interpretation/action separation | implemented | typed contracts in `wdw_behavior` |
| Explicit capability check | implemented | `wdw_tools`; full policy engine not claimed |
| Versioned viewer-scoped projection | implemented | `wdw_interfaces`, contract test |
| Deterministic loop composition | implemented | `wdw_harness`, runnable example |
| Durable database adapter | planned | no adapter in this repository |
| Production connectors and tools | planned | only protocols/boundaries are public |
| [Human Model](https://github.com/haleyparks329/the-human-model) and [Bridget](https://github.com/haleyparks329/bridget-architecture) integration | experimental | independent projects; not runtime dependencies |
| [World View](https://github.com/Wonderful-Digital-World/world-view) live adapter | planned | projection contract documented; GPL project remains separate |
| One mandatory interpreter for all evidence | intentionally rejected | domains may have zero or many interpretations |
| Central dashboard as world authority | intentionally rejected | interfaces are replaceable projections |
| Fully autonomous general resident | aspirational | authority remains bounded and explicit |
