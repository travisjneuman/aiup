# AGENTS.md — aiup

Instructions for any AI agent working in this repository. Follow the active global and workspace instructions first.

## Public Copy Style (owner rule, 2026-10-05)

Canonical copy: `tjn.portfolio/AGENTS.md`. Everything a visitor can read (site copy, README, docs pages, meta tags, titles, alt text, UI strings) must sound like Travis wrote it.

- **No em dashes (—)** anywhere public, and no spaced en dashes used as em dashes. Use a colon, a comma, parentheses, or a new sentence. Titles use ` | ` (for example `About | Site Name`).
- First person where a person is speaking, plain words, short sentences. Say what it does and what happened.
- Avoid AI tells: "not X but Y" / "rather than" setups, "built as a … surface", "demonstrates", "showcases", "leverage", "seamless", "robust", "passionate", "journey", slogans, and stacked triplets used for rhythm.
- No meta talk about the project's public positioning. If something is private, say so once, plainly.
- Only verified facts and numbers. Employers stay anonymized; named clients need Travis's OK.

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
