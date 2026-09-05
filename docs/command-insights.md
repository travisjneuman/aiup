# Understanding detected commands

AIUP reads local package metadata, app bundles, installer receipts, resolved executable paths, and recognizable launcher content. It does not run unfamiliar commands to guess their versions. Recognition provides information, not permission to update or remove a file.

## Command families reviewed on September 4, 2026

| Commands | What they belong to | How to maintain them |
|---|---|---|
| `2to3*`, `idle*`, `pip*`, `pydoc*`, `python*-config`, `python*-intel64` | Python companion commands | Update their parent Python installation. A version marked “Python” is the parent version. [Python documentation](https://docs.python.org/3/using/mac.html). |
| `python3.11` in a uv-managed directory | An interpreter installed by uv | Manage it through [uv Python support](https://docs.astral.sh/uv/guides/install-python/). |
| `corepack` | Package-manager selection for JavaScript projects | Inspect the owning installation prefix. [Corepack documentation](https://github.com/nodejs/corepack). |
| `npx` | npm's package runner | Update the npm installation that owns this exact path; another npm copy may exist. [npm documentation](https://docs.npmjs.com/cli/commands/npx). |
| `node` outside Homebrew | A separate JavaScript runtime | An installer receipt is historical evidence, not proof of the current binary version. Review alongside other Node installations. [Node.js](https://nodejs.org/). |
| `nativefier` | Builds desktop wrappers for websites | The upstream project is archived; review before reinstalling. [Nativefier repository](https://github.com/nativefier/nativefier). |
| `github` | GitHub Desktop's shell helper | Update GitHub Desktop. [Desktop documentation](https://docs.github.com/en/desktop). |
| `prlctl`, `prlsrvctl`, `prl_convert`, `prl_disk_tool`, `prl_perf_ctl`, `prlcore2dmp`, `prlexec` | Parallels app helpers | Update their parent app, not each helper. Identity is established by the resolved app path and its bundle metadata. [Parallels documentation](https://docs.parallels.com/). |
| `pwsh` | Microsoft PowerShell | Follow the original installation method. The displayed dependency-manifest value is a build version. [Microsoft installation guidance](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-macos). |
| `uvx` | uv's Python-tool launcher | Update uv. [uv tools guide](https://docs.astral.sh/uv/guides/tools/). |
| `vp` | Vite+ development toolchain | Follow the owning Vite+ installation. [Vite+](https://viteplus.dev/). |
| `yai` | AI terminal assistant | Its embedded module identity identifies the project; no automatic updater is assumed. [Yai repository](https://github.com/ekkinox/yai). |
| `agent` resolving into Grok | Alternate Grok entrypoint | Maintain Grok rather than a second tool. |
| `aiup`, `npm-update` | Updater launcher and shortcut | Maintain AIUP; the shortcut has no independent version. |
| `repo_sync.py`, `t3code-pi-acp` | Local source-managed integrations | Maintain their owning repositories or integration files. |
| `rz0`, `rz0-updater` | Locally registered Cargo packages | The registration supplies a version, not proof that a binary has never been replaced. |
| Saved `codex.pre-*` and `rz0.pre-*` files | Old wrapper or possible binary backups | Review before removing; never treat them as separate products needing updates. |

“Not reported” means a trustworthy version was not available. “Helper,” “saved copy,” “receipt,” “registered,” and “app” distinguish evidence that is not a standalone executable version. Unknown identities remain inspect-only. Custom installations may differ from the reviewed examples.

Official public sources were read through web/HTTP; local identity evidence came from files and metadata. No authenticated browser or account access was needed. The initial Parallels and Microsoft deep links failed to load; Parallels identity rests on the local app evidence, and the current Microsoft installation page was located successfully.

## Legacy JavaScript installation review — September 4, 2026

Read-only checks confirmed a separate `/usr/local/bin/node` v18.2.0 alongside Homebrew Node v26.8.1. Homebrew Node, npm, and npx occur first in the inspected shell PATH. The legacy `/usr/local/lib/node_modules` contains npm 8.9.0, Corepack 0.10.0, and Nativefier 47.2.0; `/usr/local/bin/nativefier` resolves into that directory. These are root-owned files. The Corepack pnpm/yarn entrypoint links were not present in `/usr/local/bin`.

No hard-coded `/usr/local/bin/node` or `/usr/local/lib/node_modules` references were found in the bounded shell/local-wrapper search. This does not prove that other projects or applications never use them. Nativefier remains the only detected Nativefier command, so deleting it would remove functionality. Recommendation: retain the active Homebrew installation; retire the legacy installation only after deciding Nativefier and direct Node 18 consumers are no longer needed. No packages or files were removed in this review. Nativefier's upstream archive status was rechecked through official GitHub over public HTTP; no authenticated account access or external mutation occurred.
