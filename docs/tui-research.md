# TUI research review

The catalog now has three different list sizes:

1. the curated managed catalog (small enough for an overview);
2. local detections (specific to each Mac); and
3. Homebrew's available formulae/casks (potentially tens of thousands).

These should not be presented as one undifferentiated scroll. The current TUI keeps the overview compact and makes the large views intentional.

## Implemented interaction model

| Problem | Current behavior |
|---|---|
| Too many rows at startup | Categories start collapsed. Each header shows installed/absent counts. |
| Need to move without a long scroll | Left/right collapse or expand the current category; Page Up/Page Down jumps to the previous/next category. |
| Need to jump farther | `ctrl-g` opens a searchable category palette and returns to the selected header. |
| Need a focused view | `aiup list --category CAT` focuses a managed category, `detected`, `homebrew`, or `homebrew/available`. |
| Need a compact maintenance view | `--view installed` hides absent rows; `--view managed`, `--view detected`, and `--view available` isolate the corresponding evidence lane. |
| Need to find one item | fzf's query searches the visible rows; the focused Homebrew view is generated from the user's local taps. |
| Unknown local software | A final `detected` category shows app, npm, uv, and PATH evidence as detected-only rows with source, version, and location. |
| Need context without leaving the list | The preview pane shows official docs for managed entries and source/version/path for detections. `ctrl-/` toggles the preview. |
| Risk of an accidental mutation | Detected rows never enter an update/remove action because aiup has no verified owner/updater contract for them yet. |
| Need to know what Enter will do | Rows show action badges such as `install`, `update`, `switch to Homebrew`, `sunset`, or `detected-only`; previews show dependency readiness. |

## Implemented improvements

### Faster focused workflow

- Inventory records are cached for five minutes with a source fingerprint covering PATH, application roots, package roots, and npm/uv executables. `--refresh` forces a rebuild.
- `--view installed` is the compact mode; it shows installed, on-disk, and detected rows while hiding absent managed rows.
- The full Homebrew available view builds and renders its large formula/cask index in streaming batches, keeping the broad catalog responsive instead of reopening the index for every row.

### Easier navigation

- `ctrl-g` opens a searchable category palette.
- Explicit view modes now separate `managed`, `detected`, `available`, `installed`, and `overview`.
- Homebrew available rows remain lazy and load only when the available view is focused.

### Explainable maintenance

- Visible action badges distinguish `update`, `install`, `switch to Homebrew`, `detected-only`, and lifecycle warnings.
- Previews show dependency closure and whether each prerequisite is ready or missing.
- Update runs summarize completed, removed, skipped, detected-only, failed, and cancelled work.

## Remaining improvements

- The picker remembers the last query and selected category locally; the default overview remains collapsed and users can clear the query with fzf's normal query-editing keys.

The guiding invariant is that discovery can be broad and dynamic, while mutation remains explicit, source-backed, and reversible.
