# Authority and actions

Inference may suggest useful work; it does not grant permission to perform it.
An effect must name the subject, capability, target, parameters, rationale, and
idempotency boundary. The reference `Authority.require()` demonstrates the
minimum explicit capability check.

Production policy should additionally constrain scope, time, sensitivity,
reversibility, and approval requirements. Denials and abstentions are normal
outcomes and must remain observable. An action executor should record both the
request and verified result so later reconciliation can distinguish attempt from
effect.

**Inference grants initiative, not unlimited authority.**
