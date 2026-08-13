# Portable ontology

The public ontology is intentionally small.

| Object | Meaning | Canonical? |
| --- | --- | --- |
| Artifact | Immutable received evidence plus provenance | Evidence, never interpretation |
| Interpretation | A resident's bounded reading of an artifact | No; zero or many may coexist |
| WorkItem | A durable request for bounded work | Operational state, not domain truth |
| ProposedAction | Intent to invoke a capability with a rationale | No effect until authorized |
| Outcome | `acted`, `blocked`, or `abstained`, with a reason | Final for that work item |
| Projection | Versioned, scoped rendering of world state | Disposable view, not source of truth |
| Authority | Explicit capabilities held by a subject | Yes for the attempted effect |

A domain owner—not a shared resident—owns canonical domain state. Human Model,
Bridget, and other residents may contribute interpretations under their own
contracts; none is mandatory for every artifact.
