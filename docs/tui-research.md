# TUI research review

The catalog now has three different list sizes:

1. the curated managed catalog (small enough for an overview);
2. local detections (specific to each Mac); and
3. Homebrew's available formulae/casks (potentially tens of thousands).

These should not be presented as one undifferentiated scroll. The current TUI keeps the overview compact and makes the large views intentional.

## Implemented interaction model

| Problem | Current behavior |
|---|---|
| Too many rows at startup | Categories start collapsed. Each header shows its name, a ten-cell installed bar, and `N of T installed`. |
| Need to move without a long scroll | Left/right collapse or expand the current category; Page Up/Page Down jumps to the previous/next category. |
| Need to jump farther | `ctrl-g` opens a searchable category palette and returns to the selected header. |
| Need a focused view | `aiup list --category CAT` focuses a managed category, `detected`, `homebrew`, or `homebrew/available`. |
| Need a compact maintenance view | `--view installed` hides absent rows; `--view managed`, `--view detected`, and `--view available` isolate the corresponding evidence lane. |
| Need to find one item | fzf's query searches the entire catalog, including rows inside collapsed categories; the focused Homebrew view is generated from the user's local taps. |
| Unknown local software | A final `detected` category shows app, npm, uv, and PATH evidence as detected-only rows with source, version, location, and source subtotals. |
| Need context without leaving the list | The preview pane shows official docs for managed entries and source/version/path plus a Google search for detections. `ctrl-/` toggles the preview. |
| Risk of an accidental mutation | Detected rows never enter an update action because aiup has no verified owner/updater contract. Detected app rows expose an exact-path cleanup preview and require `--apply` plus confirmation to move candidates to Trash. |
| Need to know what Enter will do | Rows show a state mark, an `on disk` note, and lifecycle tags such as `sunset`; the preview's `action` line names what Enter does and shows dependency readiness. |

## Implemented improvements

### Faster focused workflow

- Inventory records are cached for five minutes with a source fingerprint covering PATH, application roots, package roots, and npm/uv executables. `--refresh` forces a rebuild.
- `--view installed` is the compact mode; it shows installed, on-disk, and detected rows while hiding absent managed rows.
- The full Homebrew available view builds and renders its large formula/cask index in streaming batches, keeping the broad catalog responsive instead of reopening the index for every row.

### Easier navigation

- `ctrl-g` opens a searchable category palette.
- Explicit view modes now separate `managed`, `detected`, `available`, `installed`, and `overview`.
- Homebrew available rows remain lazy and load only when the available view is focused. The overview says “full Homebrew catalog not loaded” so it never shows a false zero; the explicit view separates 2,000+ `font-*` casks into `homebrew/fonts` and labels the remaining rows as non-managed Homebrew extras.

### Explainable maintenance

- The preview's `action` line distinguishes `update`, `install`, `switch to Homebrew` and detected-only rows; lifecycle warnings show on the row itself.
- Previews show dependency closure and whether each prerequisite is ready or missing. Detected previews show a Google search URL and, for app bundles, the cleanup command.
- Update runs summarize completed, removed, skipped, detected-only, failed, and cancelled work.

## List layout (2026-10-14)

With 218 entries, the flat list had become hard to scan. These changes keep the overview calm and make the state of each row readable at a glance:

- **Categories by kind of tool.** Twenty curated categories, in the order people reach for them: essentials, coding assistants and their helpers, workspaces, editors, terminals, MCP tools, sandboxes and integrations first; chat, browsers and automation next; then local models and apps, voice, image and video AI, creative apps, media tools, and utilities. Homebrew extras and detected software stay last.
- **Plain names.** Headings show a name such as **Voice and dictation**; the id (`voice`) still works with `--category`, and the category preview shows the name and a one-line description.
- **A fill bar per category.** Ten cells in the category color show how much of it is installed, next to `N of T installed` or `all N installed`. A category with any tool installed always fills at least one cell, and one with a gap never looks full.
- **State marks.** `●` installed, `◐` on disk some other way, `○` not installed, `◇` detected, `◆` manual update. Installed rows are bright and the rest are dimmed, so color is never the only signal.
- **One column rhythm.** Catalog, Homebrew, detected and Updates rows share the same bar, mark and id columns. Updates rows read `installed → available` with the new version in green.
- **Search that knows categories.** Category names are part of each tool's search text, so `voice` or `sandbox` lists a whole group. Headings hide while searching, so every hit ends with `· <category name>`.
- **A framed picker.** A rounded border labeled `aiup`, an inline match counter, a `❯` prompt, and `▶`/`✓` pointer and marker. aiup's style goes first in `FZF_DEFAULT_OPTS`, so a user's own fzf colors still win.

## State and action continuity

- The picker remembers the last query and selected category locally; the default overview remains collapsed and users can clear the query with fzf's normal query-editing keys.
- While a query is non-empty, the row source temporarily includes every category's children so collapsed categories cannot hide matches. Clearing the query returns to the compact header-only overview.
- Before and after a selected install, update, removal, or app switch, aiup restores the terminal, clears the previous full-screen frame, and then runs the provider action. Provider progress remains visible while the action is genuinely running; reopening the picker starts from a clean frame.

The guiding invariant is that discovery can be broad and dynamic, while mutation remains explicit, source-backed, and reversible.
