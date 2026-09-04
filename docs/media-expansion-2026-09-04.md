# Media catalog expansion — 2026-09-04

Runtime/catalog `2026.09.04-05`: **101 managed entries**, including **22 media tools**, plus five recognized manual-update media apps when installed. This is intentional catalog growth around AI-assisted creation and its supporting desktop/CLI tools. No applications, models, subscriptions, or account entitlements were installed or purchased by this work.

## New managed entries

Each addition uses the existing Homebrew adapter for detection, version/update checks, installation, update, and removal. Official Homebrew JSON metadata confirmed the package was neither disabled nor deprecated on the review date; app paths come from its declared artifacts. Homebrew retains OS/architecture eligibility and installer prerequisites. AIUP does not pass `--zap`; normal vendor/Homebrew uninstall hooks still apply (OBS includes virtual-camera plugin removal).

| Tool | Role | Reviewed package |
|---|---|---|
| Draw Things | Local AI image generation | [draw-things](https://formulae.brew.sh/cask/draw-things) |
| Superwhisper | AI dictation and LLM reformatting | [superwhisper](https://formulae.brew.sh/cask/superwhisper) |
| Buzz | Audio transcription and translation | [buzz](https://formulae.brew.sh/cask/buzz) |
| OBS Studio | Recording and streaming | [obs](https://formulae.brew.sh/cask/obs) |
| Blender | 3D modeling, animation, rendering | [blender](https://formulae.brew.sh/cask/blender) |
| LosslessCut | Lossless audio/video trimming | [losslesscut](https://formulae.brew.sh/cask/losslesscut) |
| HandBrake | Video transcoding | [handbrake-app](https://formulae.brew.sh/cask/handbrake-app) |
| Shotcut | Video editing | [shotcut](https://formulae.brew.sh/cask/shotcut) |
| Kdenlive | Non-linear video editing | [kdenlive](https://formulae.brew.sh/cask/kdenlive) |
| Krita | Digital painting; AI plugins are separate | [krita](https://formulae.brew.sh/cask/krita) |
| Inkscape | Vector graphics / SVG | [inkscape](https://formulae.brew.sh/cask/inkscape) |
| ImageMagick | Image processing via `magick` | [imagemagick](https://formulae.brew.sh/formula/imagemagick) |
| SoX | Audio processing | [sox](https://formulae.brew.sh/formula/sox) |
| yt-dlp | Audio/video downloading | [yt-dlp](https://formulae.brew.sh/formula/yt-dlp) |
| libvips | Efficient image processing CLI/library | [vips](https://formulae.brew.sh/formula/vips) |

Supporting creative utilities are labeled as utilities, not AI models. Vendor licenses, optional services, plugins, and model storage remain separate from catalog availability. Multiple editors are intentional choices for different workflows, not prerequisites installed together.

## Recognized manual-update apps

Exact app bundle identifiers are checked under `/Applications` and `~/Applications`. An App Store receipt's **presence** routes guidance to [App Store Updates](https://support.apple.com/guide/app-store/update-apps-fir9b01adda3/mac); receipt contents are never read. Receipt presence does not establish current account entitlement or available updates. Without a receipt, guidance remains vendor/manual.

- Final Cut Pro, Motion, Pixelmator Pro, and Darkroom receive this installed-copy-aware guidance.
- Luminar AI remains manual. The [vendor page](https://skylum.com/luminar-ai) now includes Luminar Neo marketing; it does not prove an automated update or free migration for an existing Luminar AI installation.

Manual apps keep `di:app:` identities, inspect-only dispatch, and no provider update requests. They appear once in normal browsing under media, stay available in detected-only views, and disappear from managed-only views. Preview/docs links, plain listing, coverage, and JSON inventory expose the distinction. They are **not** included in the 101 managed count. Existing cleanup remains a separate explicit preview/confirmation flow.

## Discovery correction

Registered npm sibling commands are read from package.json for managed npm/dedicated tool packages. Only executable paths that resolve to the package's declared, in-package target are grouped. A separate same-name executable remains detected. This covers Remotion's auxiliary commands without claiming arbitrary name matches belong to Remotion. Parsing and path collection are batched per inventory scan; no package code runs.

## Evidence and boundaries

Public official Homebrew metadata and Apple/vendor pages were read on TJNMPM through built-in web/API and bounded HTTPS requests. No authenticated source or browser lane was needed; no external mutation occurred. Python HTTPS initially failed local certificate verification; normal curl HTTPS succeeded without weakening TLS or changing certificates. Unresolved candidate package routes (ComfyUI/Aiko) were not converted into guessed installers. Speech generation and additional model-heavy environments remain candidates for a separately verified packaging path.

The catalog contract check passed. Focused fixtures passed bundle identity/receipt routing, manual inspect-only rows, unique identities, managed-view exclusion, protected preview materialization, exclusion from remote update checks, and sibling-path matching that preserves unrelated executables. Live read-only coverage and the media plain list recognized the five installed manual apps. No real vendor install/update/render, broad suite, or benchmark campaign was used. Owner visual acceptance remains separate.

Rollback is a Git revert. Installed apps, settings, receipts, models, user media, preferences, and logs are preserved. The release uses the existing GitHub-connected publication path without new hosted resources.
