"""Utility functions for time parsing and status emission."""

from __future__ import annotations

import logging
import math
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable
else:
    from collections import abc

    Callable = abc.Callable

from pytimeparse2 import parse as parse_duration

from ffclipper.models.verbosity import Verbosity

logger = logging.getLogger(__name__)


def parse_timespan_to_ms(s: str | None) -> int | None:
    """Convert a time string to milliseconds.

    Args:
        s: Timespan such as ``"90s"`` or ``"00:01:30"``. ``None`` or an empty
            string returns ``None``.

    Returns:
        The parsed duration in milliseconds rounded to the nearest integer.

    Raises:
        ValueError: If ``s`` cannot be parsed.

    """
    if not s:
        return None
    parsed = parse_duration(s)
    if parsed is None:
        raise ValueError(f"Unable to parse timespan: {s}")
    return round(float(parsed) * 1000)


def escape_filter_path_for_windows(path: str) -> str:
    """Normalize and escape Windows path for FFmpeg filters."""
    posix_path = PureWindowsPath(path).as_posix()
    return posix_path.replace(":", r"\:").replace("'", r"\\'")


def format_time(
    seconds: float,
    *,
    places: int = 3,
    mode: Literal["ceil", "floor", "round"] = "round",
) -> str:
    """Format seconds as ``HH:MM:SS.F`` with configurable precision."""
    q = 10**places
    if mode == "ceil":
        seconds = math.ceil(seconds * q) / q
    elif mode == "floor":
        seconds = math.floor(seconds * q) / q
    else:
        seconds = round(seconds, places)

    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:0{2 + 1 + places}.{places}f}"


def emit_status(message: str, *, status_callback: Callable[[str], None] | None) -> None:
    """Send ``message`` to the CLI, logger, or a custom callback.

    The caller controls where status lines go:

    * ``print`` - used by the CLI for direct terminal updates.
    * ``None`` - route messages through ``logger.info``.
    * Any other ``Callable[[str], None]`` - for GUIs or tests that capture
      status output.
    """
    if status_callback is None:
        logger.info(message)
        return
    # Special handling for terminal-friendly in-place updates.
    if status_callback is print:
        print(  # noqa: T201
            message,
            end="" if "\r" in message and "\n" not in message else "\n",
            flush=True,
        )
        return
    # Generic callback path.
    status_callback(message)


def format_action_label(*, dry_run: bool, cached: bool = False) -> str:
    """Return a short action label for command banners.

    - Cached: when serving from cache
    - Command: when in dry-run mode
    - Running: otherwise
    """
    if cached:
        return "Cached"
    if dry_run:
        return "Command"
    return "Running"


def maybe_log_command(
    *,
    verbosity: Verbosity,
    dry_run: bool,
    status_callback: Callable[[str], None] | None,
    banner: str,
) -> None:
    """Log a command banner when appropriate for verbosity/dry-run.

    Logs when verbosity is at least ``Verbosity.COMMANDS`` or in dry-run mode.
    """
    if verbosity >= Verbosity.COMMANDS or dry_run:
        emit_status(banner, status_callback=status_callback)


__all__ = [
    "emit_status",
    "escape_filter_path_for_windows",
    "format_action_label",
    "format_time",
    "maybe_log_command",
    "parse_timespan_to_ms",
]
