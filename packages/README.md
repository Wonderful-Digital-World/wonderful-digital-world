# Reference packages

These packages demonstrate boundaries, not a complete service topology. They
have no third-party dependencies and are intentionally small enough to inspect.

- `wdw_core`: evidence, work, outcomes, and maturity vocabulary
- `wdw_inbox`: idempotent persist-before-route semantics
- `wdw_behavior`: interpretations and proposed actions
- `wdw_connectors`: source translation protocol
- `wdw_tools`: explicit capability boundary
- `wdw_interfaces`: projection envelope and viewer authorization
- `wdw_harness`: deterministic composition of one loop iteration

Production implementations may replace every adapter while preserving these
semantics.
