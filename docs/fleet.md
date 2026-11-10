# aiup fleet

Up: [docs](README.md). Related: [scripting](scripting.md), [install](install.md).

`aiup fleet` runs aiup on this computer and on every other computer you list, all at the same time. It works the same on macOS, Linux and Windows, and any computer can start it. Plain `aiup` on each computer still updates just that computer.

```bash
aiup fleet add desk laptop pi       # SSH hosts or aliases, saved on this computer only
aiup fleet                          # update this computer and the three others
aiup fleet check                    # what each one has waiting, changes nothing
aiup fleet --dry-run                # what each one would do
```

## How it reaches the other computers

aiup uses the `ssh` you already have. For each listed host it runs `ssh HOST aiup ...` in batch mode, so a host that would ask for a password or a new host key fails right away instead of waiting. Anything ssh can reach works: a LAN, a VPN, a tailnet or the internet. Your `~/.ssh/config` aliases, users, ports, keys and jump hosts all apply.

Each remote computer needs:

- aiup installed, and on the PATH of a non-interactive SSH session. Check with `ssh HOST aiup version`. On Linux hosts whose SSH commands read no shell profile (Arch does this), install with `--system` so `/usr/local/bin/aiup` exists. See the [Linux](../linux/README.md) and [Windows](../windows/README.md) guides.
- Key-based SSH login that works without a prompt.

aiup never opens a port, runs a background service or stores credentials. It needs nothing beyond SSH.

## The fleet list

The list is a plain text file with one SSH host or alias per line. `#` starts a comment.

| System | File |
| --- | --- |
| macOS | `~/.local/share/aiup/fleet-hosts` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/aiup/fleet-hosts` |
| Windows | `%LOCALAPPDATA%\aiup\config\fleet-hosts` |

Set `AIUP_FLEET_FILE` to use another file. A host may contain only letters, digits and `. _ @ -`, and can't start with `-`, so an entry can never turn into an ssh option.

```bash
aiup fleet list                     # the list, with this computer marked
aiup fleet add HOST...              # add hosts
aiup fleet remove HOST...           # drop hosts
```

This computer always runs, locally, whether or not it's listed. If the list names this computer (by host name, its ssh `HostName`, or its Tailscale name), aiup runs it locally instead of over SSH. So you can copy the same list to every computer and start a fleet run from any of them.

## Finding computers with Tailscale

Tailscale is optional. When it's installed and running, `aiup fleet discover` lists the online Linux, macOS and Windows computers on your tailnet, asks each one for `aiup version` over SSH, and offers to add the ones that answer:

```text
$ aiup fleet discover
Asking 3 tailnet computers for `aiup version` over SSH...
  desk    windows  aiup 2026.11.10-01
  laptop  macOS    aiup 2026.11.10-01
  pi      linux    SSH works, no aiup
Add desk, laptop to the fleet list? [y/N]
```

`--add` adds them without asking. Without a terminal, discover only prints what it found. It reads the tailnet name from Tailscale and tries the short name first, then the full MagicDNS name. Without Tailscale, add hosts by name.

## What a run does

```bash
aiup fleet [update|check|plan|doctor|attention|resume|retry|version]
```

`update` (the default) runs plain `aiup` everywhere. The other words run that aiup command everywhere. `--dry-run`, `--force`, `--show-unchanged`, `--verbose` and `--refresh` pass through. No other text you type is sent to a remote shell.

Every line of output starts with the computer's name. At the end a summary shows each computer's result and time:

```text
aiup fleet: 4 computers, 3 done, 1 not
  laptop  done                          2m41s (this computer)
  desk    done                          3m05s
  pi      done                            48s
  server  could not connect over SSH       15s
Full output for each computer: ~/.local/state/aiup/fleet
```

Each computer's full output from the newest run is saved in the fleet log folder: `~/.local/share/aiup/fleet` on macOS, `${XDG_STATE_HOME:-~/.local/state}/aiup/fleet` on Linux and `%LOCALAPPDATA%\aiup\state\fleet` on Windows.

A fleet run has no terminal on the other end, so anything that needs one is put off, the same as any run without a terminal. That covers sudo password prompts, provenance questions and system package updates set to `ask`. The summary and `aiup attention` on that computer show what's left. `aiup fleet resume` retries it, or run `aiup resume` on that computer to answer the prompts. On Linux and Windows, `aiup settings system auto` on a computer lets plain runs there do system package updates without asking.

Exit status is 0 when every computer finished, 1 when any did not, 2 for a mistyped command and 130 after Ctrl-C, which stops every computer's run.
