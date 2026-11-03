# Security policy

## Supported version

aiup has no tagged release line. Security fixes ship in the next published release (the commit named in `macos/release`). Older releases and locally modified copies are not maintained as separate supported versions.

## Report a vulnerability privately

Do not open a public issue for a vulnerability or include exploit details, credentials, tokens, private inventory, or machine-specific logs in public content.

Use GitHub's **Security → Report a vulnerability** flow for this repository. Include the affected command or file, impact, reproduction conditions, and a minimal redacted proof. No response-time or disclosure-date promise is made.

Non-sensitive hardening suggestions and ordinary bugs can use the [public bug form](https://github.com/travisjneuman/aiup/issues/new?template=bug.yml).

## Security boundaries

aiup scans inventory locally. A normal run checks a small release pointer on GitHub, downloads the runtime and matching catalog only when a new release is published, and runs the last validated release when offline. It delegates selected installs or updates to Homebrew, npm, uv, GitHub releases, or documented vendor endpoints. Review [`docs/privacy.md`](docs/privacy.md) and [`docs/install.md`](docs/install.md) before reporting behavior that crosses one of those boundaries.
