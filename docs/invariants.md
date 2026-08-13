# Invariants

1. Persist evidence before acknowledgement or routing.
2. Deduplicate retries by source identity, not generated local identity.
3. Preserve source, external identity, receipt time, media type, and digest.
4. Never mutate evidence to contain an interpretation.
5. Permit zero, one, or many interpretations of the same artifact.
6. Give each canonical domain fact one declared owner.
7. Treat work state as operational state, not domain truth.
8. Record `acted`, `blocked`, or `abstained` and a reason for completed work.
9. Check explicit authority at the effect boundary.
10. Make externally visible actions idempotent or durably deduplicated.
11. Carry contract version, source revision, freshness, place, and audience on a projection.
12. Deny a projection to viewers outside its audience.
13. Preserve unknowns; absence of evidence is not negative evidence.
14. Prefer deterministic reconciliation for known failure classes.
15. Escalate ambiguity or irreversible consequences to human judgment.
16. Do not let an interface become canonical state.
17. Keep lived data out of public fixtures and documentation.
