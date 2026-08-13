# Context and projections

Context is selected world state supplied for a bounded purpose. A projection is
a rendered, versioned view of that state. Neither is a wholesale export of the
world.

The reference `Projection` requires a contract version, projection identity,
generation time, source revision, freshness budget, place, payload, and allowed
viewers. Consumers must be able to distinguish stale from current output and
must not infer authorization from possession of an identifier.

Projection producers should minimize disclosed fields, state unknowns, and use
stable semantic keys. Consumers should tolerate additive fields and reject
unsupported major contract versions.
