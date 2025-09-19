"""Verbosity levels for logging."""

from enum import IntEnum


class Verbosity(IntEnum):
    """Logging verbosity levels."""

    QUIET = 0
    COMMANDS = 1
    OUTPUT = 2


__all__ = ["Verbosity"]
