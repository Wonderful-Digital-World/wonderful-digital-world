# Command Center repository audit

Date: 2026-08-17

This is a repository-reality check for the Command Center brief. The dashboard is a projection, not a new system of record.

| Repository | Existing boundary | Command Center decision |
| --- | --- | --- |
| `wonderful-digital-world` | Shared contracts and authorized projection primitives | Own observability contracts, SQLite operator store, private Command Center, and public exporter |
| `world-view` | Separate GPL spatial interface with a `/rooms` world surface | Reuse it by URL/deep link; do not duplicate its renderer or state |
| `haleyparks329.github.io` | Astro public presentation layer | Own `/digital-world/` and `/systems/`; consume only the delayed allowlisted JSON artifact |
| resident repositories | Domain-specific execution and source state | Keep adapters minimal; emit shared observability records without adopting dashboard concerns |
| `the-human-model` | Sensitive personal data and a safe/public boundary | Export aggregates only; never project raw health or source records |
| Airtable integrations | Domain-specific experiments already exist | Keep optional; do not add a production dependency or make Airtable canonical |

## Reality findings

- `wdw_interfaces.Projection` already establishes viewer-scoped, replaceable projections.
- World View already has the spatial interface needed by `/world`; the integration seam is its public URL rather than copied rendering code.
- The public site has an established Astro layout, navigation model, and build validation pipeline.
- Core had unrelated local memory-contract work in progress when this implementation began. This work is preserved and the observability package is additive.
- No durable observability adapter existed. The local SQLite store added here is operator state and audit history, never canonical resident truth.
- No Mini Me Thought Intelligence evaluation artifact or review-write API exists in the inspected workspace. Requested counts are therefore marked unverified and all quality claims remain unavailable.
- Mini Me is the canonical writer for Thought Intelligence reviews. The Command Center has no review mutation path.

## Privacy decision

The public artifact is constructed from a fixed field allowlist and refuses release until the configured server/build-time delay has elapsed (24 hours by default). It contains aggregates and state labels only. Arbitrary source payloads, names, URLs, identifiers, review notes, and activity detail have no serialization path. Privacy regression fixtures are release blockers.
