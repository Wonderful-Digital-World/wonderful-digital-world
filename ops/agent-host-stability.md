# Native agent host stability

The Mac mini hosts Coach, Bridget and Mini Me under logged-in user LaunchAgents.
`com.wdw.agent-host-awake` runs `/usr/bin/caffeinate -is` under launchd supervision:
it prevents idle system sleep and, on AC, system sleep. It does not hold the display
awake. It starts at login; this does not make user services run before login.

Install/repair using:

```sh
~/.hermes/hermes-agent/venv/bin/python ops/agent-host-stability.py
```

The installer preserves profile settings, backs them up in WDWRuntimeState/backups,
and sets `compression.threshold_tokens: 32000` for all three Hermes profiles.
This absolute cap overrides Hermes' higher provider-specific percentage trigger.
Restart idle gateways afterward. Existing sessions will use normal Hermes
compaction on their next turn; do not delete or manually rewrite session history.

Check `pmset -g assertions` for caffeinate's PreventSystemSleep and
PreventUserIdleSystemSleep assertions, and each profile's `gateway_state.json`
for the running/connected state. To remove the assertion deliberately, boot out
`gui/$(id -u)/com.wdw.agent-host-awake` and remove its LaunchAgents plist.

Coach's routine list returns a paginated index. Full routines remain available
through `hevy_get_routine`. Read evidence above 10,000 JSON characters is saved
privately under the profile's `cache/coach-results`, keyed by SHA-256; the tool
returns exact fragments with `read_coach_result` continuation offsets. Read all
needed fragments before editing. Write receipts remain intact. Snapshots currently
persist until explicitly removed, so referenced evidence remains recoverable.

Bridget and Mini Me supervise cross-resident commands in separate process groups,
poll Hermes' thread interruption signal, enforce an actual 170-second deadline,
and terminate/reap child groups on success, cancellation, or timeout. Deadlines
also check wall time so a sleep/wake gap expires immediately after waking.
