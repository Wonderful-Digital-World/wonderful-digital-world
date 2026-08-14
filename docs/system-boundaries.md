# System boundaries

Inside WDW are durable world state, evidence, work, domain ownership, resident
protocols, policy, action records, and projection contracts.

Outside the core are:

- source systems reached through connectors;
- effect systems reached through capability-bearing tools;
- replaceable interfaces and visualizations;
- independent resident implementations such as [Human Model](https://github.com/haleyparks329/the-human-model) or [Bridget](https://github.com/haleyparks329/bridget-architecture); and
- a person's private lived data and credentials.

Connectors translate transport data and preserve provenance; they do not decide
domain meaning. Tools perform effects after authority checks; they do not infer
permission. Interfaces consume projections; they do not own world truth.

The public repository documents the seam. A real deployment must supply durable
storage, authentication, authorization policy, secrets, production connectors,
observability, and domain owners.
