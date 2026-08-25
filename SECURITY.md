# Security policy

## Supported version

aiup has no tagged release line. Security fixes target the current `main` runtime and launcher; older source revisions and locally modified copies are not maintained as separate supported versions.

## Report a vulnerability privately

Do not open a public issue for a vulnerability or include exploit details, credentials, tokens, private inventory, or machine-specific logs in public content.

Use GitHub's **Security → Report a vulnerability** flow for this repository. Include the affected command or file, impact, reproduction conditions, and a minimal redacted proof. No response-time or disclosure-date promise is made.

Non-sensitive hardening suggestions and ordinary bugs can use the [public bug form](https://github.com/travisjneuman/aiup/issues/new?template=bug.yml).

## Security boundaries

aiup scans inventory locally, refreshes its public runtime/catalog pair from GitHub on each normal invocation, and delegates selected installs or updates to Homebrew, npm, uv, GitHub releases, or documented vendor endpoints. Review [`docs/privacy.md`](docs/privacy.md) and [`docs/install.md`](docs/install.md) before reporting behavior that crosses one of those boundaries.
