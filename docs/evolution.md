# Architecture evolution

Historical documents are evidence of how the architecture changed, not canonical
specifications. Current code, contracts, tests, invariants, and explicit decisions
take precedence.

| Historical idea | Present classification | What changed |
| --- | --- | --- |
| Ambient Inbox | promoted | durable ingress, unread/acknowledged state, relevance-aware delivery |
| Universal proxy and manual refresh | superseded | typed connectors and event-driven observation |
| Mission Control event ledger | promoted | replay, idempotency, pending decisions, observable outcomes |
| Central control dashboard | superseded | no interface owns the world |
| Self-healing loop | promoted | known failure classes use deterministic verified fixes |
| Unbounded automatic repair | intentionally rejected | ambiguous or consequential work escalates |
| QA agents | promoted | shared durable state, stable fingerprints, acted/blocked/abstained |
| Project-specific QA taxonomy | narrowed | reusable protocol separated from domain vocabulary |
| Human Model as the whole world | narrowed | independent resident/domain model, not environment architecture |
| Bridget as mandatory shared reality | intentionally rejected | bounded optional interpretation; zero or many are valid |
| Character/multi-agent framing | superseded | WDW is a persistent computational environment |
| World View as core runtime | narrowed | independent projection and observability surface |

The durable pattern is movement away from humans operating dashboards and toward
evented state, explicit contracts, deterministic reconciliation, bounded agency,
and replaceable projections.
