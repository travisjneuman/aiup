## Summary

Describe the focused change and the user-visible behavior it affects.

## Validation

List the exact checks that ran and any relevant limitation. Do not claim checks that were not run.

## Checklist

- [ ] The diff is scoped to this change and contains no credentials, private inventory, personal-machine paths, or unrelated formatting.
- [ ] Public claims match the current macOS-only, online-per-run launcher contract.
- [ ] Generated catalog/docs were synchronized twice when their source changed.
- [ ] Accepted media and brand assets were not regenerated unless this pull request explicitly reviews those bytes.
- [ ] Install, update, remove, adoption, telemetry, `sudo`, `--zap`, and settings-preservation boundaries remain accurate.
