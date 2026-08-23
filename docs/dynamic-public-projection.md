# Dynamic delayed public projection

This package can produce a privacy-safe, content-addressed public snapshot after
each private WDW refresh. Producing and uploading a snapshot does not make it
public: the read service enforces a fixed 24-hour eligibility delay.

## Producer

Configure the ingest endpoint and a dedicated bearer token:

```sh
export WDW_PUBLIC_INGEST_URL="https://<website>/api/wdw/projection/ingest"
export WDW_PUBLIC_INGEST_TOKEN="<dedicated-secret>"
wdw-publish-dynamic-public --database /path/to/wdw.db
```

Use `--workspace`, `--sample`, or `--dry-run` when appropriate. The producer
constructs only the allowlisted aggregate projection before making a network
request. Retries reuse the same content-addressed snapshot ID, so successful
replays are idempotent.

Run the producer after each successful private data refresh. Its cadence is
independent of the delay; the API, not the scheduler, decides when a snapshot
is eligible.

## Safety properties

- The public payload contains aggregate systems, services, queues, and
  intelligence counts only.
- Recursive sensitive-key checks reject accidental private fields.
- The envelope fixes `eligibleAt` to exactly 24 hours after `generatedAt`.
- The payload and envelope hashes are verified again by the ingest service.
- Private source timestamps may be represented only by the delayed public
  `sourceObservedAt` field.

## Activation

Start by running the producer in dry-run mode, then point it at the shadow
ingest endpoint while leaving the current public path active. Do not retire an
existing publisher until the target environment has demonstrated correct
23:59/24:00 behavior, malformed-row last-known-good behavior, health checks,
and rollback.
