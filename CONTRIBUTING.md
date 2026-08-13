# Contributing

Contributions should make an architectural claim inspectable. Prefer a small
contract plus a test or synthetic example over a broad unimplemented API.

1. Keep personal data, credentials, private prompts, and production identifiers
   out of commits and fixtures.
2. Preserve the boundary between evidence, interpretation, proposed action, and
   authorized effect.
3. Label claims with one status from `docs/implementation-status.md`.
4. Make retries idempotent and outcomes observable.
5. Run the standard-library test suite before opening a change:

   ```sh
   PYTHONPATH=packages python3 -m unittest discover -s tests -v
   ```

Do not copy code or assets from differently licensed related projects. A new
integration with a GPL project requires an explicit license and distribution
review before code-level linking or copying.
