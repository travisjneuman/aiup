"""aiup fleet: run aiup on this computer and on other computers over SSH.

The fleet list is a plain text file with one SSH destination per line (an
alias from ~/.ssh/config, a host name, or user@host); ``#`` starts a comment.
It lives in the aiup config folder, or wherever AIUP_FLEET_FILE points. Every
computer keeps its own list, so nothing about anyone's machines is built in.

``aiup fleet`` always includes this computer, run locally, and every listed
host, run with ``ssh HOST aiup ...``. All of them run at the same time; each
output line starts with the computer's name, and each computer's full output
is also saved to a log. SSH runs in batch mode, so a host that would ask for a
password or a new host key fails fast instead of waiting. Remote hosts need
aiup on the PATH their SSH sessions get.

``aiup fleet discover`` is optional: when Tailscale is installed it lists the
online tailnet computers, asks each one for ``aiup version`` over SSH, and
offers to add the ones that answer.

macos/aiup has the same command in Bash (``fleet_main``); keep them in step.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, TYPE_CHECKING, Dict, List, Optional, Sequence, Set, Tuple

from aiup import paths
from aiup.errors import EXIT_FAILED, EXIT_INTERRUPTED, EXIT_OK, AiupError, UsageError

if TYPE_CHECKING:
    from aiup.cli import Args

# Commands aiup fleet can run everywhere. Each is a fixed word, so nothing a
# person types is ever passed through a remote shell.
RUN_COMMANDS = ("update", "check", "plan", "doctor", "attention", "resume", "retry", "version")
LIST_COMMANDS = ("list", "add", "remove", "discover")
FLEET_USAGE = ("aiup fleet [" + "|".join(RUN_COMMANDS) + "] | fleet list | fleet add HOST... | "
               "fleet remove HOST... | fleet discover [--add]")

# The flags a fleet run passes on, as (Args attribute, flag).
PASS_FLAGS = (("dry_run", "--dry-run"), ("force", "--force"), ("show_unchanged", "--show-unchanged"),
              ("verbose", "--verbose"), ("refresh", "--refresh"))

# An SSH destination: letters, digits and . _ @ -, never starting with "-" (so
# it can never be read as an ssh option).
HOST_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._@-]{0,252}$")
MAX_HOSTS = 64
SSH_OPTIONS = ("-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=4")
PROBE_OPTIONS = ("-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8")
LOOPBACK = ("localhost", "127.0.0.1", "::1")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_NOT_FOUND_WINDOWS = "is not recognized as an internal or external command"


# ----- the fleet list --------------------------------------------------------------


def fleet_file(os_name: str, env: Optional[Dict[str, str]] = None) -> Path:
    """AIUP_FLEET_FILE, else ``fleet-hosts`` in the aiup config folder."""
    env = dict(os.environ) if env is None else env
    override = env.get("AIUP_FLEET_FILE", "")
    if override:
        return Path(override).expanduser().absolute()
    return paths.dirs_for(os_name, env).config / "fleet-hosts"


def log_dir(os_name: str) -> Path:
    """Where each computer's output from the newest fleet run is kept."""
    return paths.dirs_for(os_name, dict(os.environ)).state / "fleet"


def check_host(host: str) -> str:
    """The host, or a UsageError when it is not a plain SSH destination."""
    if not HOST_RE.match(host):
        raise UsageError("'{}' is not an SSH host name or alias (letters, digits and . _ @ - only)"
                         .format(host[:80]))
    return host


def _entry(line: str) -> str:
    """The host on one line of the fleet file, or "" for blanks and comments."""
    return line.split("#", 1)[0].strip()


def read_lines(path: Path) -> List[str]:
    """The fleet file's lines, or none when it does not exist yet."""
    paths.refuse_symlink(path)
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise AiupError("could not read " + str(path) + ": " + (exc.strerror or str(exc))) from exc


def read_hosts(path: Path) -> List[str]:
    """Hosts in file order, each once (case-insensitive), skipping bad lines with a warning."""
    hosts: List[str] = []
    seen: Set[str] = set()
    for number, line in enumerate(read_lines(path), 1):
        host = _entry(line)
        if not host:
            continue
        if not HOST_RE.match(host):
            sys.stderr.write("aiup: skipping line {} of {}: not an SSH host\n".format(number, path))
            continue
        if host.lower() not in seen:
            seen.add(host.lower())
            hosts.append(host)
    if len(hosts) > MAX_HOSTS:
        raise AiupError("the fleet list has more than {} hosts: {}".format(MAX_HOSTS, path))
    return hosts


def write_lines(path: Path, lines: Sequence[str]) -> None:
    """Replace the fleet file in one step."""
    paths.ensure_dir(path.parent)
    paths.refuse_symlink(path)
    temp = path.with_name("." + path.name + ".tmp-" + str(os.getpid()))
    try:
        temp.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        os.replace(str(temp), str(path))
    except OSError as exc:
        try:
            temp.unlink()
        except OSError:
            pass
        raise AiupError("could not write " + str(path) + ": " + (exc.strerror or str(exc))) from exc


def add_hosts(path: Path, new: Sequence[str]) -> List[str]:
    """Append hosts not already listed; returns the ones added."""
    lines = read_lines(path)
    known = {_entry(line).lower() for line in lines}
    added: List[str] = []
    for host in new:
        if host.lower() not in known:
            known.add(host.lower())
            added.append(host)
    if len(known - {""}) > MAX_HOSTS:
        raise AiupError("a fleet list holds at most {} hosts".format(MAX_HOSTS))
    if added:
        if not lines:
            lines = ["# aiup fleet: one SSH host or alias per line. This computer always runs too."]
        write_lines(path, lines + added)
    return added


def remove_hosts(path: Path, gone: Sequence[str]) -> List[str]:
    """Drop lines naming these hosts; returns the ones that were listed."""
    wanted = {host.lower() for host in gone}
    kept: List[str] = []
    removed: List[str] = []
    for line in read_lines(path):
        host = _entry(line)
        if host and host.lower() in wanted:
            removed.append(host)
        else:
            kept.append(line)
    if removed:
        write_lines(path, kept)
    return removed


# ----- which entry is this computer ------------------------------------------------


def _norm(name: str) -> str:
    """First DNS label, lowercase, letters and digits only (Work-Laptop.lan -> worklaptop)."""
    return re.sub(r"[^a-z0-9]", "", name.strip().rstrip(".").split(".")[0].lower())


def _looks_like_address(host: str) -> bool:
    return bool(re.match(r"^[0-9.]+$", host)) or ":" in host


def _quiet_output(argv: Sequence[str], timeout: float) -> Optional[str]:
    """A command's stdout, or None when it cannot run or fails."""
    try:
        done = subprocess.run(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "replace")


def tailscale_command(os_name: str) -> Optional[str]:
    """The Tailscale CLI, from PATH or its usual install folder."""
    found = shutil.which("tailscale")
    if found:
        return found
    if os_name == "windows":
        base = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = Path(base) / "Tailscale" / "tailscale.exe"
    elif os_name == "darwin":
        candidate = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    else:
        return None
    return str(candidate) if candidate.is_file() else None


def tailscale_status(os_name: str) -> Optional[Dict[str, object]]:
    """``tailscale status --json``, or None without Tailscale or when it is not running."""
    command = tailscale_command(os_name)
    if command is None:
        return None
    text = _quiet_output([command, "status", "--json"], 15)
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def self_names(os_name: str, status: Optional[Dict[str, object]]) -> Set[str]:
    """Normalized names this computer goes by."""
    names = {_norm(socket.gethostname())}
    if os_name == "windows":
        names.add(_norm(os.environ.get("COMPUTERNAME", "")))
    me = status.get("Self") if status else None
    if isinstance(me, dict):
        for key in ("DNSName", "HostName"):
            value = me.get(key)
            if isinstance(value, str):
                names.add(_norm(value))
    names.discard("")
    return names


def ssh_hostname(ssh: str, host: str) -> str:
    """The host name ssh would connect to for this destination (``ssh -G``)."""
    text = _quiet_output([ssh, "-G", host], 5) or ""
    for line in text.splitlines():
        if line.startswith("hostname "):
            return line.split(" ", 1)[1].strip()
    return ""


def is_self(entry: str, names: Set[str], ssh: Optional[str]) -> bool:
    """Whether a fleet entry names this computer."""
    host = entry.rsplit("@", 1)[-1]
    candidates = [host]
    if ssh is not None:
        resolved = ssh_hostname(ssh, host)
        if resolved:
            candidates.append(resolved)
    for candidate in candidates:
        if candidate.lower() in LOOPBACK:
            return True
        if not _looks_like_address(candidate) and _norm(candidate) in names:
            return True
    return False


# ----- running ---------------------------------------------------------------------


@dataclass
class Target:
    """One computer in a fleet run."""

    label: str
    argv: List[str]
    local: bool = False


@dataclass
class Outcome:
    """How one computer's run ended."""

    target: Target
    code: int = EXIT_FAILED
    seconds: float = 0.0
    log: Optional[Path] = None
    not_found: bool = False
    process: Optional["subprocess.Popen[bytes]"] = field(default=None, repr=False)


def local_argv(words: Sequence[str]) -> List[str]:
    """This aiup, run again with the same Python and release."""
    python = os.environ.get("AIUP_PYTHON", "") or sys.executable
    runtime = os.environ.get("AIUP_ACTIVE_RUNTIME", "")
    if not runtime:
        runtime = str(Path(__file__).resolve().parent.parent.parent / "aiup_main.py")
    return [python, runtime] + list(words)


def remote_words(args: "Args") -> List[str]:
    """The aiup command line every computer runs."""
    command = args.subcommand or "update"
    words = [] if command == "update" else [command]
    for attr, flag in PASS_FLAGS:
        if getattr(args, attr, False):
            words.append(flag)
    return words


def _clean(line: str) -> str:
    return _CONTROL.sub("", _ANSI.sub("", line))


def _safe_name(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", label)[:100] or "host"


class _Printer:
    """Writes prefixed lines from many threads without mixing them."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.lock = threading.Lock()

    def line(self, label: str, text: str) -> None:
        with self.lock:
            try:
                sys.stdout.write("{:<{w}}  {}\n".format(label, text, w=self.width))
                sys.stdout.flush()
            except (OSError, ValueError, UnicodeEncodeError):
                pass


def _show(outcome: Outcome, printer: _Printer, raw: bytes) -> None:
    text = _clean(raw.decode("utf-8", "replace").rstrip("\r\n"))
    if _NOT_FOUND_WINDOWS in text:
        outcome.not_found = True
    printer.line(outcome.target.label, text)


def _follow(outcome: Outcome, printer: _Printer, process: "subprocess.Popen[bytes]",
            reader: IO[bytes]) -> None:
    """Print the log as the child writes it, until the child exits and the log is read out."""
    pending = b""
    exited = False
    while True:
        chunk = reader.read(65536)
        if chunk:
            lines = (pending + chunk).split(b"\n")
            pending = lines.pop()
            for raw in lines:
                _show(outcome, printer, raw)
        elif exited:
            break
        elif process.poll() is not None:
            exited = True
        else:
            time.sleep(0.2)
    if pending:
        _show(outcome, printer, pending)


def _run_one(outcome: Outcome, printer: _Printer, logs: Path) -> None:
    # The child writes straight to its log file, never to a pipe: Windows ssh.exe
    # does not exit while its output is a pipe this process made.
    target = outcome.target
    start = time.monotonic()
    log_path = logs / (_safe_name(target.label) + ".log")
    writer: Optional[IO[bytes]] = None
    try:
        writer = open(str(log_path), "wb")
        reader = open(str(log_path), "rb")
    except OSError as exc:
        if writer is not None:
            writer.close()
        printer.line(target.label, "could not open its log: " + (exc.strerror or str(exc)))
        outcome.code = EXIT_FAILED
        return
    outcome.log = log_path
    with writer, reader:
        try:
            process = subprocess.Popen(target.argv, stdin=subprocess.DEVNULL, stdout=writer,
                                       stderr=subprocess.STDOUT)
        except OSError as exc:
            printer.line(target.label, "could not start: " + (exc.strerror or str(exc)))
            outcome.code = 127
            return
        outcome.process = process
        writer.close()
        _follow(outcome, printer, process, reader)
    outcome.code = process.wait()
    outcome.seconds = time.monotonic() - start


def _duration(seconds: float) -> str:
    whole = int(seconds + 0.5)
    if whole < 60:
        return "{}s".format(whole)
    return "{}m{:02d}s".format(whole // 60, whole % 60)


def _describe(outcome: Outcome) -> str:
    code = outcome.code
    if code == 0:
        return "done"
    if not outcome.target.local and code == 255:
        return "could not connect over SSH"
    if code == 127 or outcome.not_found:
        return "aiup not found on its PATH"
    if code == EXIT_INTERRUPTED:
        return "stopped"
    return "something failed (exit {})".format(code)


def run_targets(targets: Sequence[Target], logs: Path) -> List[Outcome]:
    """Run every target at once, streaming prefixed output; Ctrl-C stops them all."""
    paths.ensure_dir(logs)
    width = max(len(t.label) for t in targets)
    printer = _Printer(width)
    outcomes = [Outcome(target=t) for t in targets]
    threads = [threading.Thread(target=_run_one, args=(o, printer, logs), daemon=True) for o in outcomes]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            while thread.is_alive():
                thread.join(0.2)
    except KeyboardInterrupt:
        for outcome in outcomes:
            if outcome.process is not None and outcome.process.poll() is None:
                try:
                    outcome.process.terminate()
                except OSError:
                    pass
        raise
    return outcomes


def build_targets(os_name: str, hosts: Sequence[str], words: Sequence[str],
                  ssh: Optional[str]) -> Tuple[List[Target], List[str]]:
    """This computer first, then each listed host that is not this computer."""
    names = self_names(os_name, tailscale_status(os_name))
    local_label = ""
    remote: List[str] = []
    for host in hosts:
        if is_self(host, names, ssh):
            local_label = local_label or host
        else:
            remote.append(host)
    if not local_label:
        local_label = socket.gethostname().split(".")[0].lower() or "this-computer"
    targets = [Target(label=local_label, argv=local_argv(words), local=True)]
    if remote and ssh is None:
        raise AiupError("ssh is not on PATH, so aiup fleet cannot reach the other computers")
    for host in remote:
        targets.append(Target(label=host, argv=[str(ssh)] + list(SSH_OPTIONS) + [host, "aiup"] + list(words)))
    return targets, remote


def _summary(outcomes: Sequence[Outcome], logs: Path) -> int:
    width = max(len(o.target.label) for o in outcomes)
    good = sum(1 for o in outcomes if o.code == 0)
    out = sys.stdout
    out.write("\naiup fleet: {} computer{}, {} done, {} not\n".format(
        len(outcomes), "" if len(outcomes) == 1 else "s", good, len(outcomes) - good))
    for outcome in outcomes:
        note = " (this computer)" if outcome.target.local else ""
        out.write("  {:<{w}}  {:<28} {:>7}{}\n".format(outcome.target.label, _describe(outcome),
                                                      _duration(outcome.seconds), note, w=width))
    out.write("Full output for each computer: {}\n".format(logs))
    if any(o.code == 255 and not o.target.local for o in outcomes):
        out.write("A host that could not connect needs key-based SSH that works with "
                  "`ssh HOST aiup version` (no password or host-key prompt).\n")
    out.flush()
    return EXIT_OK if good == len(outcomes) else EXIT_FAILED


def run_fleet(args: "Args", os_name: str) -> int:
    """aiup fleet [COMMAND]: run on this computer and every listed host."""
    path = fleet_file(os_name)
    hosts = read_hosts(path)
    ssh = shutil.which("ssh")
    words = remote_words(args)
    targets, remote = build_targets(os_name, hosts, words, ssh)
    if not remote:
        sys.stdout.write("aiup fleet: no other computers are listed in {}\n"
                         "Add some with aiup fleet add HOST..., or aiup fleet discover with Tailscale. "
                         "Running here only.\n\n".format(path))
    logs = log_dir(os_name)
    shown = " ".join(["aiup"] + words)
    sys.stdout.write("aiup fleet: running `{}` on {}\n".format(
        shown, ", ".join(t.label for t in targets)))
    sys.stdout.flush()
    outcomes = run_targets(targets, logs)
    return _summary(outcomes, logs)


# ----- list, add, remove -----------------------------------------------------------


def list_hosts(os_name: str) -> int:
    path = fleet_file(os_name)
    hosts = read_hosts(path)
    ssh = shutil.which("ssh")
    names = self_names(os_name, tailscale_status(os_name))
    out = sys.stdout
    out.write("Fleet list: {}\n".format(path))
    if not hosts:
        out.write("  (empty) aiup fleet runs on this computer only.\n"
                  "  Add hosts with aiup fleet add HOST..., or aiup fleet discover with Tailscale.\n")
        return EXIT_OK
    for host in hosts:
        out.write("  {}{}\n".format(host, "  (this computer)" if is_self(host, names, ssh) else ""))
    return EXIT_OK


def add_command(os_name: str, words: Sequence[str]) -> int:
    hosts = [check_host(word) for word in words]
    path = fleet_file(os_name)
    added = add_hosts(path, hosts)
    for host in hosts:
        sys.stdout.write("{} {}\n".format("added" if host in added else "already listed:", host))
    if added:
        sys.stdout.write("Saved in {}. Check each with: ssh HOST aiup version\n".format(path))
    return EXIT_OK


def remove_command(os_name: str, words: Sequence[str]) -> int:
    hosts = [check_host(word) for word in words]
    removed = {host.lower() for host in remove_hosts(fleet_file(os_name), hosts)}
    status = EXIT_OK
    for host in hosts:
        if host.lower() in removed:
            sys.stdout.write("removed {}\n".format(host))
        else:
            sys.stdout.write("not listed: {}\n".format(host))
            status = EXIT_FAILED
    return status


# ----- discover --------------------------------------------------------------------


@dataclass
class Peer:
    """An online tailnet computer and what it said over SSH."""

    short: str
    fqdn: str
    os: str
    answer: str = ""        # the host name that answered, short or full
    version: str = ""


def tailnet_peers(status: Dict[str, object]) -> List[Peer]:
    """Online Linux, macOS and Windows peers, by name."""
    found: List[Peer] = []
    raw = status.get("Peer")
    values = raw.values() if isinstance(raw, dict) else []
    for peer in values:
        if not isinstance(peer, dict) or not peer.get("Online"):
            continue
        system = str(peer.get("OS", ""))
        if system.lower() not in ("linux", "macos", "windows"):
            continue
        fqdn = str(peer.get("DNSName", "")).rstrip(".")
        short = fqdn.split(".")[0] if fqdn else str(peer.get("HostName", ""))
        short = short.lower()
        if HOST_RE.match(short):
            found.append(Peer(short=short, fqdn=fqdn if HOST_RE.match(fqdn) else "", os=system))
    return sorted(found, key=lambda p: p.short)


def _probe(ssh: str, peer: Peer) -> Peer:
    """Ask the peer for aiup version, by short name and then by full name."""
    for name in (peer.short, peer.fqdn):
        if not name:
            continue
        # A temporary file, not a pipe: see _run_one.
        try:
            with tempfile.TemporaryFile() as out:
                done = subprocess.run([ssh] + list(PROBE_OPTIONS) + [name, "aiup", "version"],
                                      stdin=subprocess.DEVNULL, stdout=out,
                                      stderr=subprocess.DEVNULL, timeout=60, check=False)
                out.seek(0)
                text = out.read(65536).decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 255:
            continue
        lines = [_clean(x).strip() for x in text.splitlines()]
        lines = [x for x in lines if x]
        peer.answer = name
        if done.returncode == 0 and lines:
            peer.version = lines[-1][:40]
        return peer
    return peer


def discover(os_name: str, add_all: bool) -> int:
    status = tailscale_status(os_name)
    if status is None:
        raise AiupError("aiup fleet discover needs Tailscale installed and running. Without it, "
                        "add hosts by name: aiup fleet add HOST...")
    ssh = shutil.which("ssh")
    if ssh is None:
        raise AiupError("ssh is not on PATH")
    peers = tailnet_peers(status)
    if not peers:
        sys.stdout.write("No other Linux, macOS or Windows computers are online on this tailnet.\n")
        return EXIT_OK
    sys.stdout.write("Asking {} tailnet computer{} for `aiup version` over SSH...\n".format(
        len(peers), "" if len(peers) == 1 else "s"))
    sys.stdout.flush()
    with ThreadPoolExecutor(max_workers=min(8, len(peers))) as pool:
        peers = list(pool.map(lambda p: _probe(ssh, p), peers))
    path = fleet_file(os_name)
    listed = {h.lower() for h in read_hosts(path)}
    width = max(len(p.short) for p in peers)
    addable: List[str] = []
    for peer in peers:
        if peer.version:
            state = "aiup " + peer.version
        elif peer.answer:
            state = "SSH works, no aiup"
        else:
            state = "SSH did not connect"
        is_listed = peer.short in listed or (peer.fqdn and peer.fqdn.lower() in listed)
        if is_listed:
            state += ", listed"
        elif peer.version:
            addable.append(peer.answer)
        sys.stdout.write("  {:<{w}}  {:<8} {}\n".format(peer.short, peer.os, state, w=width))
    if not addable:
        sys.stdout.write("Nothing new to add.\n")
        return EXIT_OK
    if not add_all:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            sys.stdout.write("Add them with aiup fleet discover --add, or aiup fleet add {}\n"
                             .format(" ".join(addable)))
            return EXIT_OK
        try:
            answer = input("Add {} to the fleet list? [y/N] ".format(", ".join(addable)))
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            sys.stdout.write("Nothing changed.\n")
            return EXIT_OK
    added = add_hosts(path, addable)
    sys.stdout.write("Added {} to {}\n".format(", ".join(added) or "nothing", path))
    return EXIT_OK


# ----- entry -----------------------------------------------------------------------


def run(args: "Args", ctx: object = None) -> int:
    """Dispatch aiup fleet's subcommands."""
    os_name = args.os_name
    sub = args.subcommand or "update"
    if sub == "list":
        return list_hosts(os_name)
    if sub == "add":
        return add_command(os_name, args.words)
    if sub == "remove":
        return remove_command(os_name, args.words)
    if sub == "discover":
        return discover(os_name, args.fleet_add)
    return run_fleet(args, os_name)
