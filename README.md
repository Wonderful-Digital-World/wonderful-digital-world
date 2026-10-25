# Wonderful Digital World

[![CI](https://github.com/Wonderful-Digital-World/wonderful-digital-world/actions/workflows/ci.yml/badge.svg)](https://github.com/Wonderful-Digital-World/wonderful-digital-world/actions/workflows/ci.yml)

A persistent environment of AI agents that run my life's operations on a Mac mini:
a coach, a coordinator, a writing partner and an engineer. They share one
knowledge base and one rule book, hand work to each other with receipts, report
every night, and read a structured model of me instead of chat history. I built
and operate all of it; this repository holds its architecture, its observability
service (Command Center) and small executable reference contracts.

> The human provides the human things. The computer handles the computer things.

## What runs today

```mermaid
flowchart TB
    H["Me (Telegram)"] --> B["Bridget<br/>front door, coordination"]
    H --> C["Coach<br/>training and nutrition"]
    H --> M["Mini Me<br/>writing and reflection"]
    B -- "route_request<br/>(receipts)" --> R["Routing service"]
    R --> C & M & K["Banjo<br/>engineering"]
    C & B & M & K <--> L["Shared Library<br/>Git + Markdown notes, RULES.md"]
    C & B & M --> HM["Human Model<br/>Postgres, append-only ledgers,<br/>lift and readiness models"]
    A["Agent Inbox<br/>durable file receipts"] --> C & B
    N["Nightly job 21:30<br/>standups, huddle, Inbox sorting,<br/>service health"] --> B
    HM & L --> CC["Command Center<br/>(this repository)"]
    CC --> WV["World View<br/>pixel-art view of the agents"]
```

| Part | What it does | Code |
|---|---|---|
| **Residents** | Four long-running agents (Hermes and OpenClaw), each with its own Telegram bot or route, memory and tools. A routing policy assigns each a model tier under a monthly budget cap. | private |
| **Front door and routing** | Bridget takes any request and routes it to the specialist with `route_request`; a loopback service records the request, the delivery and the reply, so "accepted" is never mistaken for "done". | private |
| **Shared Library** | A Git repository of typed Markdown notes (observation, hypothesis, decision, work report) that agents write through one service: author stamped, deduplicated by source, corrected by supersession, never edited. Agents leave each other addressed notes; I read it as an Obsidian graph. | private |
| **One rule book** | `RULES.md` has an Everyone section, a section per group and one per agent; each agent's prompt gets only its own subset when it is deployed. | private |
| **Human Model** | The structured model of me the agents read: workouts, check-ins, health data, messages, predictions and outcomes in append-only Postgres tables, with a read grant per agent. | [the-human-model](https://github.com/haleyparks329/the-human-model) (engine public) |
| **Nightly standup** | Each agent reports its day and answers notes addressed to it; then a huddle where each may message one teammate; then Bridget sorts the Inbox into the Library and texts me a short summary, leading with any failed service. | private |
| **Command Center** | Read-only observability: resident status, health, needs-attention items and recent activity from every repository's projections. | [`packages/wdw_observability`](packages/wdw_observability) |
| **World View** | A pixel-art world where the agents live; their notes to each other play as speech bubbles. | [world-view](https://github.com/Wonderful-Digital-World/world-view) |
| **Pinned deploys** | Every service runs through [`ops/canonical-exec`](ops/canonical-exec), which refuses to start unless the checkout is at the exact deployed commit. A deploy is an explicit re-pin, so nothing changes by accident. | [`ops/canonical-exec`](ops/canonical-exec) |

## Engineering choices

- **Deterministic where possible, agentic where valuable.** Routing receipts,
  identity, idempotency, permissions and pins are ordinary code; models do
  interpretation and judgment.
- **Durable state outlives the agent.** Work, evidence and decisions live in the
  Library, the Human Model and the routing ledger, not in a chat transcript, so a
  model or framework can be swapped without losing anything.
- **Evidence is typed.** A report, a hypothesis and a verified result are
  different kinds of record, and a note saying "done" is not proof.
- **Hexagonal and replaceable.** Each domain exposes ports; the lift model's
  signal reader, for example, is keyword-based or LLM-based behind one interface.
- **Honest records.** Predictions, outcomes and experiments are append-only,
  including the ones that failed.

## Run it

Requires Python 3.11 or newer; the reference packages have no runtime dependencies.

```sh
python3 -m pip install pytest
python3 -m pytest
PYTHONPATH=packages python3 examples/ingress_to_projection.py
```

Start with [architecture](docs/architecture.md), [ontology](docs/ontology.md)
and [invariants](docs/invariants.md). The [persistent-world example](examples/ingress_to_projection.py)
is the shortest executable tour.

## Why this exists

Most software still makes the human act as its integration and orchestration
layer. The human has to remember which system owns what, move information
between tools, repeat context the computer has already seen, and reconstruct
decisions already made. They notice failed automation, route obvious work, keep
boards and interfaces synchronized, and learn each tool's internal abstractions
just to express intent.

Adding an LLM or chatbot does not necessarily remove that burden. A
conversational interface can still leave the human responsible for persistent
state, routing, synchronization, retries, permissions, source-of-truth choices,
context reconstruction, and operational monitoring. It may make commands easier
to phrase without changing who operates the control plane.

> **Why is the human still the orchestration layer?**

WDW's response is to move mechanical coordination into persistent software
while preserving human authority where intent, judgment, consent, taste,
ambiguity, or consequences make human involvement valuable. This is a
human-in-the-loop system with explicit authority boundaries and domain
ownership—not a system that uses the human as its runtime integration layer.

## The architectural bet

WDW is organized around four bets.

### The world persists independently of conversation

Conversation is one interface into durable state, not the canonical state
itself. Work, evidence, outcomes, and domain state survive the process, model,
or interface handling them.

### Deterministic software provides structure; AI provides reasoning

Use deterministic mechanisms where guarantees matter: persistence, identity,
idempotency, known-rule routing, permissions, provenance, lifecycle, retries,
budgets and enforcement, and canonical mutation.

Use probabilistic model reasoning where ambiguity earns its cost:
interpretation, synthesis, recommendations, contextual prioritization,
uncertain classification, and judgment.

> **Deterministic where possible; agentic where valuable.**

> **LLMs are components, not the architecture.**

### Domains retain ownership

Bounded contexts own their canonical state. Residents and interfaces may
interpret evidence, propose actions, and produce projections, but they do not
silently become canonical owners of the state they consume.

### Human judgment remains at meaningful boundaries

The goal is not to remove the human from the loop. It is to move the human to
the part of the loop where human contribution matters.

> **Move the human to the right part of the loop.**

Mechanical coordination should disappear into software. Consequential judgment
remains human-controlled.

## Core concepts

The architecture diagram rests on a small vocabulary:

- **Evidence** — source-backed information that retains provenance.
- **Domain state** — canonical state owned by the appropriate domain.
- **WorkItem** — durable work that survives the worker performing it.
- **Resident** — a bounded specialist with its own responsibility and authority.
- **Projection** — a viewer-scoped, non-canonical representation of world state.
- **Proposed action** — a recommendation for change, not permission to mutate
  canonical state.
- **Interface** — a port into the world, not the world itself.
- **Place** — a stable contextual address where residents, projections, and
  interactions can be situated without making the visual layout canonical.

See the [portable ontology](docs/ontology.md) for the formal distinctions.

## Human-centered is a technical constraint

In WDW, human-centered computing is not visual-design branding. It is an
engineering constraint: reduce cognitive load and interaction cost; make
changing one's mind cheap; treat repeated manual work as a systems signal; and
preserve uncertainty instead of inventing facts. Observability should match
useful human mental models without exposing the entire human model.

That leads to minimum-sufficient-context projections, least-privilege authority,
clear provenance, and interfaces that can be replaced without replacing the
world beneath them. HCI concerns therefore shape abstraction boundaries,
contextual projections, and control-plane design.

> **A feature should reduce operation, not relocate it.**

> **The interface is disposable; the model persists.**

## Architecture evolution

WDW was not designed fully formed. It evolved through experiments in human
modeling, continuity, QA automation, self-healing systems, and observability.
The [architecture history](docs/evolution.md) records which ideas were promoted,
rejected, narrowed, or superseded as those boundaries were learned through
implementation.

## Public reference implementation

The Python packages implement and test a deliberately small seam through the
architecture:

- immutable evidence with provenance and content digests;
- idempotent, persist-before-routing inbox behavior;
- durable work items with `acted`, `blocked`, and `abstained` outcomes;
- evidence/interpretation/proposed-action separation;
- explicit capability checks for effects;
- versioned, freshness-aware, viewer-authorized projections; and
- one deterministic observe/understand/reconcile iteration.

These claims describe only the executable public repository. They do not claim
parity with, or disclose the maturity and contracts of, any private deployment.
This is a reference implementation, not a deployable personal world. See
[implementation status](docs/implementation-status.md) before building on it.

## Repository map

- `docs/`: architecture, boundaries, authority, evolution, and status
- `packages/`: small executable contracts, separated by responsibility
- `examples/`: runnable synthetic flows
- `fixtures/`: synthetic data only
- `diagrams/`: source-controlled diagrams
- `residents/`: resident protocol, not private resident implementations
- `ops/`: `canonical-exec` and host stability notes
- `tests/`: executable architectural invariants

## Related projects

These projects are independently implemented and are not WDW packages:

- **[The Human Model](https://github.com/haleyparks329/the-human-model)** explores longitudinal representation of a changing person:
  evidence, uncertainty, interventions, outcomes, and canonical human-domain
  state.
- **[Bridget](https://github.com/haleyparks329/bridget-architecture)** explores persistent continuity and reconciliation through a bounded
  resident rather than a universal assistant or gateway.
- **[QA Agents](https://github.com/haleyparks329/qa-agents)** contributed patterns for durable shared state, stable issue
  fingerprints, advisory routing, and explicit outcomes without becoming part of
  WDW.
- **[World View / Tiny Places](https://github.com/Wonderful-Digital-World/world-view)**
  explores visual projection and observability over the persistent world while
  remaining independently implemented and GPL-separated.

See [relationships](docs/relationships.md) and the detailed
[World View / Tiny Places boundary](docs/world-view-tiny-places.md).

## License

Code and documentation in this repository are available under the [MIT License](LICENSE).
Third-party projects retain their own licenses.
