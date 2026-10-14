# Update notifications | aiup

`aiup notify` checks for updates and shows a macOS notification when some are ready. It installs nothing. aiup never schedules it for you: if you want it to run on its own, add a cron job or a launchd agent yourself, using one of the examples below.

## What it does

```bash
aiup notify            # check, notify if the list of ready updates changed
aiup notify --always   # check, notify whenever updates are ready
```

1. It runs the same read-only check as `aiup check`.
2. It prints one line, for example:
   `aiup: 3 updates ready: codex 0.48.0 -> 0.49.0, gemini 0.11.2 -> 0.11.3, wrangler 4.42.0 -> 4.43.1. Run aiup to install them.`
   or `aiup: everything is up to date.`
3. When updates are ready, it shows a notification titled "aiup" ("3 updates ready", then the first three names).
4. It remembers which updates it told you about (`~/.local/share/aiup/notify-last.txt`). The next run notifies again only when that list changes, so a daily job does not repeat the same notification. `--always` skips that and notifies every time.

Exit status: 0 after a check (with or without updates), 1 when the check could not run, 2 for a mistyped option.

Scheduled jobs start with a short `PATH`. `aiup notify` adds `~/.local/bin`, `/usr/local/bin`, `/usr/local/sbin`, `/opt/homebrew/bin` and `/opt/homebrew/sbin` (the ones that exist) before it checks, so it finds the same tools your shell does.

## Run it every morning with launchd (recommended)

A launchd agent runs inside your login session, so its notifications show up reliably. Save this as `~/Library/LaunchAgents/com.example.aiup-notify.plist`, with your user name in the two paths:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.aiup-notify</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOUR-NAME/.local/bin/aiup</string>
    <string>notify</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/YOUR-NAME/Library/Logs/aiup-notify.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOUR-NAME/Library/Logs/aiup-notify.log</string>
</dict>
</plist>
```

Load it once:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.aiup-notify.plist
```

If the Mac is asleep at 9:00, launchd runs it when the Mac wakes. To stop it:

```bash
launchctl bootout "gui/$(id -u)/com.example.aiup-notify"
```

Then delete the plist file.

## Run it with cron

`crontab -e`, then add a line like this one (every day at 9:00):

```
0 9 * * * $HOME/.local/bin/aiup notify >> $HOME/Library/Logs/aiup-notify.log 2>&1
```

cron does not run while the Mac sleeps, and on recent macOS versions a notification from a cron job may not appear. The log line is always written, so you can check it there. launchd avoids both problems.

## The first notification

macOS shows notifications from `aiup notify` through Script Editor's notification permission. The first time, macOS may ask whether to allow them, or put them straight into Notification Center. If nothing appears, open System Settings > Notifications > Script Editor and allow notifications.

## What it costs

A check is the same as `aiup check`: one small request per installed tool to the source it installs from, and a Homebrew metadata refresh when it is older than 15 minutes. Answers are cached, so a second run soon after is quick. `aiup notify` does not look up release notes; `aiup check` and `aiup plan` do that when you want to read them.

## Using the output in your own scripts

For a script that needs every detail, use `aiup check --json` instead. It prints the full results as JSON on stdout (schema `aiup-check-v1`):

```bash
aiup check --json | python3 -c 'import json,sys; print([t["tool"] for t in json.load(sys.stdin)["tools"] if t["result"] == "update"])'
```
