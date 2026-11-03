"""What a run will do for each tool, before anything changes (design doc 6.5, 7.3, 9.1).

For each requested tool: preferences (exclusions, holds), the channel
resolution, the installed copy, the latest version (with the self-updated
rule: a copy at or past what its channel offers is never touched, so it is
never downgraded) and the provider's action. Reads run in parallel; nothing
here changes a tool.

Package ids (``pkg:<manager>:<name>``) are packages you installed with a
user-level package manager that no catalog tool covers. A plain run updates
them like Homebrew extras on macOS (``update_installed_brew_extra``), on the
managers in :data:`EXTRAS_MANAGERS` only: Linuxbrew on Linux, Scoop on
Windows (design section 2.1). Packages on system managers are left to
``aiup system``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Mapping, Optional, Sequence, Set, Tuple

from aiup.model import EMPTY_RESULTS, Action, CatalogEntry, Installed, Latest, Target

from aiup.engine import host
from aiup.engine.channels import Copy, Resolution, channel_label, find_copies, hook_for, resolve
from aiup.engine.latest import classify, prefetch_outdated, read_latest, self_updated_note
from aiup.engine.prefs import ChannelChoices, Preferences, policy_reason

if TYPE_CHECKING:
    from aiup.catalog.loader import Catalog
    from aiup.engine.context import Context
    from aiup.providers.base import Provider

INFRA_CATEGORY = "infra"
PACKAGES_CATEGORY = "packages"
PACKAGE_PREFIX = "pkg:"
OS_LABELS = {"linux": "Linux", "windows": "Windows", "darwin": "macOS"}
# User-level managers whose explicitly installed extras a plain run updates (section 2.1).
EXTRAS_MANAGERS: Mapping[str, Tuple[str, ...]] = {"linux": ("brew",), "windows": ("scoop",)}
# Packages another updater owns (macOS: node belongs to the npm updater, not a Homebrew extra).
EXTRAS_SKIP: Mapping[str, Tuple[str, ...]] = {"brew": ("node",)}


@dataclass
class Job:
    """One tool in a run."""

    tool: str
    op: str                                   # install | update
    explicit: bool
    entry: Optional[CatalogEntry] = None
    resolution: Optional[Resolution] = None
    target: Optional[Target] = None
    provider: Optional["Provider"] = None
    installed: Optional[Installed] = None     # copy on the active channel at plan time
    latest: Optional[Latest] = None
    status: str = "run"                       # run | skipped | current | self-updated | deferred | failed
    note: str = ""
    before: str = "not installed"
    action: Optional[Action] = None
    retire: Tuple[Copy, ...] = ()
    notes: List[str] = field(default_factory=list)

    @property
    def package(self) -> bool:
        """True for a ``pkg:<manager>:<name>`` job (a package outside the catalog)."""
        return self.tool.startswith(PACKAGE_PREFIX)

    @property
    def category(self) -> str:
        """The catalog category, ``packages`` for a package job, "" when unknown."""
        if self.entry is not None:
            return self.entry.category
        return PACKAGES_CATEGORY if self.package else ""

    @property
    def channel(self) -> str:
        """The active channel ("" when none)."""
        return self.target.channel if self.target is not None else ""

    @property
    def lane(self) -> str:
        """The provider's lane; "main" for exclusive providers and when unknown."""
        if self.provider is None or self.provider.exclusive:
            return "main"
        return self.provider.lane or "main"

    def stop(self, status: str, note: str) -> None:
        """Mark the job as not running, with a reason."""
        self.status = status
        self.note = note


def order_tools(catalog: "Catalog", tools: Sequence[str]) -> List[str]:
    """Infrastructure first (macOS ``main_update``), package ids last, otherwise the given order."""
    unique = list(dict.fromkeys(tools))
    def rank(tool: str) -> int:
        if tool.startswith(PACKAGE_PREFIX):
            return 2
        entry = catalog.get(tool)
        return 0 if entry is not None and entry.category == INFRA_CATEGORY else 1
    return sorted(unique, key=rank)


def plan_jobs(ctx: "Context", catalog: "Catalog", tools: Sequence[str], op: str, explicit: bool,
              prefs: Preferences, choices: ChannelChoices, installed_only: bool = False) -> List[Job]:
    """Plan every tool. ``op`` is "update" or "install".

    ``installed_only`` drops tools with no copy here instead of listing them
    as skipped (a plain run, macOS ``installed_update_tools``); the installed
    read is the same one the plan uses, so nothing is read twice.
    """
    jobs = resolve_jobs(ctx, catalog, tools, op, explicit, prefs, choices, installed_only)
    providers = {job.provider.name: job.provider for job in jobs
                 if job.status == "run" and job.provider is not None and job.op == "update"}
    prefetch_outdated(ctx, providers.values())
    _parallel(ctx, jobs, lambda job: _finish(ctx, job))
    return jobs


def resolve_jobs(ctx: "Context", catalog: "Catalog", tools: Sequence[str], op: str, explicit: bool,
                 prefs: Preferences, choices: ChannelChoices, installed_only: bool = False) -> List[Job]:
    """Preferences, channel resolution and the installed copy, without latest versions or actions.

    ``aiup check`` stops here; :func:`plan_jobs` goes on to plan the actions.
    """
    jobs = [Job(tool=t, op=op, explicit=explicit, entry=catalog.get(t)) for t in order_tools(catalog, tools)]
    _parallel(ctx, jobs, lambda job: _resolve(ctx, job, prefs, choices, installed_only))
    if installed_only:
        jobs = [job for job in jobs if job.status != ABSENT]
    return jobs


ABSENT = "absent"   # installed_only: not here, so not part of the run


def installed_ids(ctx: "Context", catalog: "Catalog") -> List[str]:
    """Every catalog id offered here, then the package ids a plain run updates.

    Pass the result to :func:`plan_jobs` with ``installed_only=True``.
    """
    return [entry.id for entry in catalog.available_on(ctx.os_name)] + extras_ids(ctx, catalog)


def extras_ids(ctx: "Context", catalog: "Catalog") -> List[str]:
    """``pkg:<manager>:<name>`` for packages installed on request on this OS's extras managers.

    Packages a catalog tool covers (macOS ``catalog_covers_brew``) and
    packages another updater owns are left out.
    """
    out: List[str] = []
    for manager in EXTRAS_MANAGERS.get(ctx.os_name, ()):
        if not ctx.provider_available(manager):
            continue
        provider = ctx.provider(manager)
        if provider is None:
            continue
        try:
            records = list(provider.inventory(ctx) or ())
        except (OSError, ValueError, NotImplementedError):
            continue
        covered = _covered(ctx, catalog, manager)
        skip = EXTRAS_SKIP.get(manager, ())
        for record in records:
            name = record.name
            if not name or not record.explicit or record.scope != "user":
                continue
            if name in skip or _short(name) in covered:
                continue
            out.append(PACKAGE_PREFIX + manager + ":" + name)
    return list(dict.fromkeys(out))


def _covered(ctx: "Context", catalog: "Catalog", manager: str) -> Set[str]:
    """Package names a catalog tool installs through ``manager`` (tap or bucket dropped)."""
    found: Set[str] = set()
    for entry in catalog.available_on(ctx.os_name):
        for target in entry.targets_for(ctx.os_name):
            if target.channel == manager and target.package:
                found.add(_short(target.package))
    return found


def _short(package: str) -> str:
    return package.rsplit("/", 1)[-1]


def _parallel(ctx: "Context", jobs: List[Job], work: Callable[[Job], None]) -> None:
    todo = [job for job in jobs if job.status == "run"]
    if not todo:
        return
    workers = max(1, min(len(todo), ctx.config.check_workers))

    def guarded(job: Job) -> None:
        try:
            work(job)
        except Exception as exc:  # noqa: BLE001  one provider bug must not stop the others
            job.stop("failed", "Could not plan " + job.tool + ": " + type(exc).__name__ + ".")

    host.map_threads(workers, guarded, todo)


def _resolve(ctx: "Context", job: Job, prefs: Preferences, choices: ChannelChoices,
             installed_only: bool = False) -> None:
    entry = job.entry
    if entry is None and job.package:
        _resolve_package(ctx, job, prefs, installed_only)
        return
    if entry is None:
        job.stop("failed", "Unknown tool: " + job.tool)
        return
    copies: Optional[Tuple[Copy, ...]] = None
    if installed_only:
        if not entry.available_on(ctx.os_name):
            job.stop(ABSENT, "")
            return
        copies = find_copies(entry, ctx)
        if not copies:
            job.stop(ABSENT, "")
            return
    if job.op == "update":
        reason = policy_reason(prefs, job.tool)
        if reason:
            job.stop("skipped", reason)
            return
    if not entry.available_on(ctx.os_name):
        job.stop("skipped" if job.op == "update" else "failed",
                 "No {} install channel for {} yet.".format(OS_LABELS.get(ctx.os_name, ctx.os_name), job.tool))
        return
    res = resolve(entry, ctx.os_name, choices.policy, choices.picks, ctx, copies)
    job.resolution = res
    if res.active is None:
        job.stop("skipped" if job.op == "update" and not job.explicit else "failed", res.reason)
        return
    job.target = res.active
    job.provider = ctx.provider(res.active.channel)
    if job.provider is None:
        job.stop("failed", channel_label(res.active.channel) + " is not available on this computer.")
        return
    job.installed = res.copy_on(res.active.channel)
    first = res.installed[0][1] if res.installed else None
    shown = job.installed or first
    job.before = (shown.version or "unknown") if shown is not None else "not installed"
    _choose_op(job, res)


def _resolve_package(ctx: "Context", job: Job, prefs: Preferences, installed_only: bool) -> None:
    """A ``pkg:<manager>:<name>`` job: updates only, on this OS's extras managers."""
    _, manager, name = (job.tool.split(":", 2) + ["", ""])[:3]
    if job.op != "update" or manager not in EXTRAS_MANAGERS.get(ctx.os_name, ()) or not name:
        job.stop("skipped", "aiup updates only {} packages in a run; aiup system covers the rest.".format(
            " and ".join(channel_label(m) for m in EXTRAS_MANAGERS.get(ctx.os_name, ())) or "no"))
        return
    target = Target(channel=manager, package=name)
    provider = ctx.provider(manager) if ctx.provider_available(manager) else None
    installed: Optional[Installed] = None
    if provider is not None:
        try:
            installed = provider.installed(ctx, target)
        except (OSError, ValueError, NotImplementedError):
            installed = None
    if installed is None:
        if installed_only:
            job.stop(ABSENT, "")
        else:
            job.stop("skipped", "No longer installed through " + channel_label(manager) + ".")
        return
    reason = policy_reason(prefs, job.tool)
    if reason:
        job.stop("skipped", reason)
        return
    job.target, job.provider, job.installed = target, provider, installed
    job.before = installed.version or "unknown"


def _choose_op(job: Job, res: Resolution) -> None:
    if not res.installed:
        if job.op == "update" and not job.explicit:
            job.stop("skipped", "Not installed; install with: aiup only " + job.tool)
            return
        job.op = "install"
        return
    if job.installed is None:
        # Installed elsewhere: install on the active channel, then retire the old copies.
        job.op = "install"
        job.retire = res.retire
        job.notes.append("Moving from {} to {}.".format(
            " and ".join(channel_label(t.channel) for t, _ in res.installed), channel_label(job.channel)))
        move_note = hook_for(job.tool).move_note
        if move_note:
            job.notes.append(move_note)
        if res.kept_note:
            job.notes.append(res.kept_note)
        return
    job.retire = res.retire
    if job.op == "install":
        job.op = "update"


def _finish(ctx: "Context", job: Job) -> None:
    """Latest version, the self-updated rule, and the provider's action."""
    provider, target = job.provider, job.target
    if provider is None or target is None:
        return
    if job.op == "update" and job.installed is not None:
        current = job.installed.version
        latest = read_latest(ctx, provider, target, job.tool, current, during_run=True)
        job.latest = latest
        kind = classify(current, latest)
        if kind == "skipped":
            job.stop("skipped", latest.managed)  # another updater owns it (Microsoft Store)
            return
        if kind == "self-updated":
            job.stop("self-updated", self_updated_note(current, channel_label(target.channel), latest.version))
            return
        if kind == "current" and not ctx.force:
            job.stop("current", "")
            return
    if job.op == "install" and not _can_provide(ctx, provider, target):
        where = channel_label(target.channel)
        moving = job.resolution is not None and bool(job.resolution.installed)
        job.stop("skipped" if moving else "failed",
                 "{} cannot install {} here: its configured repositories or remotes do not have it. "
                 "Nothing changed.".format(where, target.package))
        return
    try:
        action = provider.update(ctx, target) if job.op == "update" else provider.install(ctx, target)
    except NotImplementedError:
        job.stop("failed", channel_label(target.channel) + " support is not finished in this runtime yet.")
        return
    except (OSError, ValueError) as exc:
        job.stop("failed", "Could not plan {}: {}".format(job.tool, str(exc)[:160]))
        return
    job.action = action
    if action.note:
        job.notes.append(action.note)
    if not action.steps:
        job.stop(empty_result(action), action.note or "Nothing to run.")


def _can_provide(ctx: "Context", provider: "Provider", target: Target) -> bool:
    """``Provider.can_provide``; a read that fails counts as yes, so the install itself reports it."""
    try:
        return bool(provider.can_provide(ctx, target))
    except (AttributeError, NotImplementedError, OSError, ValueError):
        return True


def empty_result(action: Action) -> str:
    """The one rule for an action without steps: it never counts as done.

    The provider's ``action.result`` says how to report it (skipped,
    deferred, self-updated or failed) and ``action.note`` says why. Without a
    result, an install is failed and an update or a removal is skipped.
    """
    if action.result in EMPTY_RESULTS:
        return action.result
    return "failed" if action.op == "install" else "skipped"


def plan_note(job: Job) -> str:
    """Notes collected while planning, as one line."""
    return " ".join(dict.fromkeys(n for n in job.notes if n))
