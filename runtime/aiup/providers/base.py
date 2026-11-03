"""The provider interface (design doc section 6.2).

Providers describe; the engine acts. A provider never runs a mutating command
itself. It returns :class:`Action` objects and the engine runs their steps,
which keeps dry-run, logging, progress, sudo handling and Ctrl-C in one place.

Reads go through ``ctx.run_read(argv, timeout, max_bytes, cwd=, env=)`` and
HTTP reads through ``ctx.net``.

The optional hooks at the end (``can_provide`` to ``explain_exit``) have safe
defaults, so the engine calls them on every provider: ``lock_held`` before
any step, ``explain_exit`` when a step ends with a non-zero status,
``forget`` after every step that ran, ``notices`` after ``aiup system``, and
``can_provide`` before an install. ``unavailable_reason`` and ``owns_many``
are for doctor and detection.

An action without steps is never a success. Set ``Action.result`` to
"skipped", "deferred", "self-updated" or "failed" and say why in
``Action.note``; without a result an install counts as failed and an update
or removal as skipped.

A provider module defines one subclass of :class:`Provider` whose ``name`` is
its channel. The registry in :mod:`aiup.providers` finds it, or a module-level
``PROVIDER`` instance when the module sets one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, FrozenSet, Iterable, Mapping, Optional, Sequence, Tuple

from aiup.model import Action, Installed, Latest, Ownership, PackageRecord, Step, Target

if TYPE_CHECKING:
    from aiup.engine.context import Context

__all__ = ["Action", "Installed", "Latest", "Ownership", "PackageRecord", "Provider", "Step", "Target"]

PROVIDER_SCOPES = ("user", "system", "mixed")


class Provider:
    """One install channel. Subclasses set the class attributes and the reads."""

    name: str = ""                      # channel name, section 6.3
    oses: FrozenSet[str] = frozenset()  # {"linux"}, {"windows"}, {"linux", "windows", "darwin"}
    scope: str = "user"                 # "user" | "system" | "mixed"
    lane: str = "main"                  # lane key for parallel runs (section 9.1)
    exclusive: bool = False             # True: runs alone, never beside another lane
    targeted_update: bool = True        # False: one package cannot be updated safely (pacman)

    def available(self, ctx: "Context") -> bool:
        """True when this channel's manager is present and usable here."""
        raise NotImplementedError(self.name + ".available")

    def installed(self, ctx: "Context", target: Target) -> Optional[Installed]:
        """The copy this channel installed, or None."""
        raise NotImplementedError(self.name + ".installed")

    def latest(self, ctx: "Context", target: Target, timeout: float) -> Latest:
        """The newest version this channel offers for the target."""
        raise NotImplementedError(self.name + ".latest")

    def outdated(self, ctx: "Context") -> Mapping[str, Latest]:
        """Optional bulk read of outdated packages, keyed by package."""
        return {}

    def inventory(self, ctx: "Context") -> Iterable[PackageRecord]:
        """Every package this manager has installed (section 8)."""
        return ()

    def install(self, ctx: "Context", target: Target) -> Action:
        """Steps that install the target."""
        raise NotImplementedError(self.name + ".install")

    def update(self, ctx: "Context", target: Target) -> Action:
        """Steps that update the target."""
        raise NotImplementedError(self.name + ".update")

    def remove(self, ctx: "Context", target: Target) -> Action:
        """Steps that remove the target."""
        raise NotImplementedError(self.name + ".remove")

    def owns(self, ctx: "Context", path: str) -> Optional[Ownership]:
        """Which package of this manager owns ``path``, or None."""
        return None

    def system_upgrade(self, ctx: "Context") -> Optional[Action]:
        """``aiup system`` steps. Only system-scope providers return one."""
        return None

    def metadata_refresh(self, ctx: "Context") -> Optional[Action]:
        """A metadata refresh (apt-get update); the engine runs it at most once per run."""
        return None

    # ----- optional hooks with defaults ------------------------------------------

    def can_provide(self, ctx: "Context", target: Target) -> bool:
        """True when this channel can install the target here (its repository has it).

        Asked before an install only. The default trusts the catalog.
        """
        return True

    def lock_held(self, ctx: "Context") -> str:
        """A note while another process holds this manager's lock, else ""."""
        return ""

    def notices(self, ctx: "Context") -> Tuple[str, ...]:
        """Lines to show after ``aiup system`` (pacman: new .pacnew files)."""
        return ()

    def owns_many(self, ctx: "Context", paths: Sequence[str]) -> Dict[str, Ownership]:
        """Ownership for many paths at once; the default asks ``owns`` for each."""
        found: Dict[str, Ownership] = {}
        for path in paths:
            owner = self.owns(ctx, path)
            if owner is not None:
                found[path] = owner
        return found

    def unavailable_reason(self, ctx: "Context") -> str:
        """Why this channel cannot be used here, for doctor; "" when it can or nothing is known."""
        return ""

    def forget(self) -> None:
        """Drop cached reads; the engine calls it after every step that ran."""
        return None

    def explain_exit(self, op: str, code: Optional[int]) -> Optional[Tuple[str, str]]:
        """``(result, note)`` for a non-zero exit status, or None for no reading.

        ``result`` is one of failed, deferred, cancelled, skipped, unchanged,
        self-updated, or "" to keep the engine's own result and add the note.
        On a status in ``Step.ok_codes`` only the note is used.
        """
        return None

    def supports(self, os_name: str) -> bool:
        """True when this provider runs on ``os_name``."""
        return os_name in self.oses

    def __repr__(self) -> str:
        return "<Provider {}>".format(self.name or type(self).__name__)
