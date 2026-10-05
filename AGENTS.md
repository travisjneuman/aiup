# AGENTS.md — aiup

Instructions for any AI agent working in this repository. Follow the active global and workspace instructions first.

## Showcase facts contract

This repo is showcased on travisjneuman.com and github.com/travisjneuman.
`showcase.json` is the only source for public facts about this project
(schema: travisjneuman/travisjneuman `showcase/schema/showcase-v1.json`).

- If a change affects anything in it (counts, version, status, stack, links,
  summary), update `showcase.json` in the same commit. Re-run each metric's
  `source` command; never guess. `floor-2sig` metrics round down to two
  significant digits plus "+" (398 -> "390+").
- Set `updated` (and the touched metric's `asOf`) to today's date.
- Never put private URLs, hostnames, user data, or private names in it.
- The profile repo's `scripts/showcase/sync-showcase.mjs` regenerates the GitHub
  cards, README table, and portfolio data from these files.
