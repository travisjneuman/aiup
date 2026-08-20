# Linux

Not implemented yet. The macOS script in `macos/aiup` is the current implementation.

When the port lands it will:

- Keep the same catalog ids and commands (`aiup`, `aiup list`, `aiup install`, `aiup remove`)
- Scan locally (PATH, app dirs, distro packages) with nothing uploaded
- Prefer vendor installers and user prefixes — never `sudo`
- Treat Homebrew as optional, not required
