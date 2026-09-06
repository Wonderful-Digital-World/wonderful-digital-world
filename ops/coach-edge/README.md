# Coach edge Gate 1 operator setup

These files are inert examples. Gate 1 does not install a launch agent, create a
Cloudflare resource, publish DNS, or place a secret on a machine.

## Boundary

The edge listens only on `127.0.0.1:4380`, calls only the Coach service at
`127.0.0.1:4350`, and initially exposes only `coach_get_status` at
`POST /v1/tools/coach_get_status`. Every other path and tool is denied. The
status response contains availability plus configured identity and revision
metadata; it does not proxy the Coach runtime response.

External callers must pass both Cloudflare Access service-token headers and the
application bearer token:

```text
CF-Access-Client-Id: <service-token-client-id>
CF-Access-Client-Secret: <service-token-client-secret>
Authorization: Bearer <random-per-Coach-token>
```

Cloudflare terminates TLS and enforces Access before the outbound-only tunnel
can reach the loopback edge. The application credential is a separate control.

## Manual setup

1. Commission and record the exact Coach, Harness, and generated identity
   revisions. Do not substitute repository `HEAD` for the commissioned Coach
   revision.
2. Create a private config directory and private state directory owned by the
   service user. Set both to mode `0700`.
3. Generate a high-entropy bearer token, for example with
   `openssl rand -base64 48`. Store the plaintext only in the calling secret
   manager. Put its SHA-256 digest in a private copy of
   `credentials.example.json`, set the allowed operator actor ID, and set the
   file to mode `0600`.
4. Install this repository into a dedicated virtual environment. Copy
   `com.wdw.coach-edge.plist.example` outside the repository, replace every
   placeholder, validate it with `plutil -lint`, then load it manually with
   `launchctl bootstrap gui/$(id -u) <absolute-plist-path>`.
5. Confirm the edge is loopback-only with `lsof -nP -iTCP:4380 -sTCP:LISTEN`.
   The listener address must be `127.0.0.1`, never `*`, a LAN address, or a
   public address.
6. Install `cloudflared`, authenticate the intended Cloudflare account with
   `cloudflared tunnel login`, create a named tunnel with
   `cloudflared tunnel create coach-edge`, and route the chosen hostname with
   `cloudflared tunnel route dns coach-edge <hostname>`.
7. In Cloudflare Zero Trust, create a self-hosted Access application for the
   exact hostname. Create a service token and an Access policy whose only
   include rule is that service token. Do not create a bypass policy.
8. Copy `cloudflared-config.yml.example` outside the repository, replace the
   tunnel UUID, credential path, and hostname, then run
   `cloudflared tunnel ingress validate` against that private config.
9. Copy `com.cloudflare.cloudflared.coach-edge.plist.example` outside the
   repository, replace every placeholder, validate it with `plutil -lint`, and
   load it manually with `launchctl bootstrap` as in step 4.
10. From the external caller, send the three authentication headers above and
    JSON `{"contractVersion":"1","residentId":"coach"}` to
    `https://<hostname>/v1/tools/coach_get_status`. Confirm a trace ID is
    returned in `X-WDW-Trace-Id` and the response exposes no arbitrary Coach
    runtime fields.
11. Confirm requests without Access credentials are rejected at Cloudflare,
    requests without the bearer are rejected by the edge, and non-allowlisted
    paths such as `/v1/invocations` and tools such as `read_file` return 404.

## Rotation, revocation, and logs

Rotate by generating a new random bearer, replacing the digest atomically in
the private credential file, and updating the caller's secret. The edge reloads
the credential file for every request. Revoke immediately by setting
`"revoked": true` or removing the entry; then revoke the Cloudflare service
token independently.

The application writes a bounded rotating JSONL audit log containing timestamp,
trace ID, tool, outcome, and HTTP status only. It never
logs authorization headers, bearer tokens, request bodies, response bodies, or
conversation content. Cloudflare retention and redaction must be configured
separately to the same minimum-data standard.

## Rollback

Unload the two launch agents with `launchctl bootout`, revoke the Cloudflare
service token, remove the tunnel hostname, and revoke/remove the application
credential entry. The underlying Coach loopback service is unchanged.
