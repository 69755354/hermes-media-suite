"""Exit-code contract and exceptions.

Exit codes are copied verbatim from the Mac deployment README section 7 and
must not be renumbered (remote support reads them from logs):
  0 all green / 2 gate red / 3 skipped (lock/memory/browser already open) /
  4 storage not writable / 5 config or key error / 6 canary not armed.
"""

EXIT_OK = 0
EXIT_GATE_RED = 2
EXIT_SKIP = 3
EXIT_STORAGE = 4
EXIT_CONFIG = 5
EXIT_CANARY = 6

EXIT_MEANING = {
    EXIT_OK: "all green",
    EXIT_GATE_RED: "gate red",
    EXIT_SKIP: "skipped (lock/memory/browser already open)",
    EXIT_STORAGE: "storage not writable",
    EXIT_CONFIG: "config or key error",
    EXIT_CANARY: "canary not armed",
}


class WinPortError(Exception):
    """Base class. Carries an exit code for the CLI layer."""

    exit_code = EXIT_CONFIG

    def __init__(self, message, *, exit_code=None, details=None, code=None):
        super().__init__(message)
        self.message = message
        if exit_code is not None:
            self.exit_code = exit_code
        self.details = details or {}
        self.code = code


class StorageNotWritable(WinPortError):
    exit_code = EXIT_STORAGE


class LockHeld(WinPortError):
    exit_code = EXIT_SKIP


class GateRed(WinPortError):
    exit_code = EXIT_GATE_RED


class NoSubmitExit(GateRed):
    """Expected control-flow exit after a fill-only rehearsal.

    This is deliberately a distinct subclass so the CLI can recycle the
    RESERVED ledger entry without freezing the whole channel.
    """


class ConfigError(WinPortError):
    exit_code = EXIT_CONFIG


class CanaryNotArmed(WinPortError):
    exit_code = EXIT_CANARY
