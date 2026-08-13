# Persistent world

Persistence means more than saving chat transcripts. A world can be reconstructed
and continued because it durably records:

- immutable evidence and provenance;
- current domain state and its owner;
- pending and completed work;
- interpretations with authorship and confidence;
- actions, authority decisions, idempotency keys, and outcomes; and
- projection revisions and freshness metadata.

The reference `Inbox` is in-memory so its behavior is easy to inspect; it proves
contracts, not durability across process restarts. A production adapter must make
the persist-before-acknowledge and deduplication boundaries transactional.

Continuity belongs to the model. A UI can disappear, change form, or be rebuilt
without erasing the world: **The interface is disposable; the model persists.**
