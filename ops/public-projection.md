# Public projection operations

The public World and Systems pages consume a delayed, allowlisted projection rather than private resident state. A run creates a sanitized candidate immediately, then releases the newest eligible candidate only after its full 24-hour hold.

Run `wdw-publish-public` every 30–60 minutes from the private host. Point `--workspace` at the private WDW workspace, `--state-root` at private durable storage, and `--website-repo` at a clean checkout of the website repository. Add `--commit --push` for the production publisher.

The command refuses a non-root repository, unrelated staged changes, unexpected publication paths, invalid schemas, broken hashes, and candidates that have not completed the delay. Operational events remain under the private state root in `operations.jsonl`; only `public/projections/wdw/manifest.v1.json` and immutable release artifacts enter the website repository.

Install and edit `ops/com.wonderfuldigitalworld.public-projection.plist.example` to run it hourly on macOS. Keep its state and logs outside every public repository.
