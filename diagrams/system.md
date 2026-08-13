# System diagram

```mermaid
flowchart LR
    Sources["Source systems"] --> Connectors["Connectors: translate + preserve provenance"]
    Connectors --> Inbox["Durable inbox: persist + deduplicate"]
    Inbox --> World["Persistent world"]
    World --> Understand["Understand: bounded interpretations"]
    Understand --> Reconcile["Reconcile: desired vs observed"]
    Reconcile --> Policy["Authority + policy"]
    Policy --> Tools["Tools: effects"]
    Tools --> Sources
    Tools --> World
    World --> Projection["Versioned authorized projection"]
    Projection --> Interfaces["Replaceable interfaces / World View"]
    Interfaces -->|"bounded intent"| Policy
```

The diagram shows responsibility and data boundaries, not mandatory deployment
services. Any agentic component belongs inside a bounded understanding or
proposal step; it does not bypass persistence or authority.
