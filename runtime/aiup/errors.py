"""Exit codes and the errors that map onto them (design doc section 2.3).

0 done, 1 something failed or was refused, 2 mistyped input, 130 Ctrl-C.
Raise one of these from anywhere; :func:`aiup.cli.main` prints its one line on
stderr and exits with its code.
"""

from __future__ import annotations

from typing import Optional

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


class AiupError(Exception):
    """A failure that ends the command with one line on stderr and exit 1."""

    exit_code = EXIT_FAILED

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def render(self) -> str:
        """The one line printed on stderr."""
        return "aiup: " + self.message


class UsageError(AiupError):
    """Mistyped command, option or missing argument (exit 2).

    Same wording as ``usage_error`` in macos/aiup:
    ``aiup: unknown command 'chek'. Run aiup help.``
    """

    exit_code = EXIT_USAGE

    def render(self) -> str:
        return "aiup: " + self.message + ". Run aiup help."


class PlatformUnsupported(AiupError):
    """A known command that does not apply on this platform (exit 1)."""

    def __init__(self, command: str, substitute: str = "", only_on: str = "macOS") -> None:
        text = command + " is " + only_on + " only."
        if substitute:
            text += " " + substitute
        super().__init__(text)
        self.command = command
        self.substitute = substitute


class NotImplementedOnSystem(AiupError):
    """A command whose module is not part of this runtime yet (exit 1)."""

    def __init__(self, command: str) -> None:
        super().__init__(command + " isn't implemented on this system yet")
        self.command = command


class CatalogError(AiupError):
    """The catalog files are missing or break the schema (exit 1).

    ``location`` names the file, and the line and column when known, so the
    message points at the exact cell to fix.
    """

    def __init__(self, message: str, location: Optional[str] = None) -> None:
        full = message if not location else location + ": " + message
        super().__init__(full)
        self.location = location


class Interrupted(AiupError):
    """Stopped with Ctrl-C (exit 130)."""

    exit_code = EXIT_INTERRUPTED

    def __init__(self, message: str = "stopped") -> None:
        super().__init__(message)
