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
| Need a focused view | `aiup list --category CAT` focuses a managed category, `detected`, `homebrew`, or `homebrew/available`. |
| Need to find one item | fzf's query searches the visible rows; the focused Homebrew view is generated from the user's local taps. |
| Unknown local software | A `detected` category shows app, npm, uv, and PATH evidence as read-only rows. |
| Need context without leaving the list | The preview pane shows official docs for managed entries and source/version/path for detections. `ctrl-/` toggles the preview. |
| Risk of an accidental mutation | Detected rows never enter an update/remove action. Their preview explicitly says aiup will not guess an owner or updater. |

## Recommended next improvements

### P0: keep the focused workflow fast

- Persist the last focused category and query, but keep the default overview collapsed.
- Cache inventory records with a timestamp and invalidate only when the relevant source changes. A full app-bundle scan should not repeat when the user only reopens the picker.
- Add a compact mode that hides absent managed entries and shows only installed, detected, and on-disk rows.

### P1: make large catalogs navigable

- Add a category jump palette (`ctrl-g`) with counts and a direct search field.
- Add explicit view modes: `managed`, `detected`, `available`, and `all`.
- Add sort choices for label, source, version, and recently detected.
- Keep Homebrew available rows lazy: load the available category only when focused, never during the normal overview scan.

### P2: make maintenance explainable

- Add a visible action badge: `update`, `install`, `switch to Homebrew`, `read-only`, or `sunset`.
- Show dependency closure in the preview before an install, including whether a missing tap will require confirmation.
- Add a result summary that distinguishes updated, skipped, detected-only, failed, and user-cancelled items.

The guiding invariant is that discovery can be broad and dynamic, while mutation remains explicit, source-backed, and reversible.
