"""Helpers for executing FFmpeg and ffprobe commands."""

import logging
import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from ffclipper.models.context import RuntimeContext

from .helpers import emit_status

_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"

_FFMPEG_VERSION_KEY = "__ffmpeg_version__"

_VIDEO_FILTER = "-vf"

logger = logging.getLogger(__name__)


def cache_key(cmd: Sequence[str | Path]) -> tuple[Any, ...]:
    """Return a cache key for ``cmd`` based on tokens and file metadata."""
    key_parts: list[Any] = []
    for token in cmd:
        s = str(token)
        key_parts.append(s)
        if s.startswith("-"):
            continue
        path = Path(s)
        if path.is_file():
            try:
                stat = path.stat()
            except OSError:
                # File might disappear or be unreadable; skip metadata defensively
                continue
            key_parts.extend([int(stat.st_mtime_ns), stat.st_size])
    return tuple(key_parts)


def _run_streaming(
    cmd: list[str],
    *,
    creationflags: int,
    log: Callable[[str], None],
) -> str:
    """Run a command, streaming combined stdout/stderr and returning output."""
    with subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=creationflags,
    ) as p:
        output_chunks: list[str] = []
        if p.stdout is None:  # pragma: no cover - defensive
            raise RuntimeError("Failed to capture subprocess stdout")
        buf = ""
        for line in iter(p.stdout.readline, ""):
            output_chunks.append(line)
            parts = line.split("\r")
            buf += parts[0]
            for part in parts[1:]:
                log(buf + "\r")
                buf = part
            if buf.endswith("\n"):
                log(buf[:-1])
                buf = ""
        if buf:
            log(buf)
            buf = ""
        p.wait()
        output = "".join(output_chunks)
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode or 1, cmd, output)
        return output


def run(
    exe: str | Path,
    args: Sequence[str | Path],
    *,
    verbose: bool = False,
    status_callback: Callable[[str], None] | None = None,
    list_cmd: bool = False,
) -> str:
    """Run an executable and return its combined stdout/stderr.

    When ``verbose`` is ``True``, stream output lines to the provided
    ``status_callback`` (or the logger) as the process runs. Otherwise capture
    output and return it after completion.
    """
    cmd = [str(exe), *[str(a) for a in args]]

    def log(message: str, *, debug: bool = False) -> None:
        if debug:
            # Debug output never goes to the status callback; keep it in logs.
            logger.debug(message)
        else:
            emit_status(message, status_callback=status_callback)

    # Only emit a one-line banner when explicitly requested via list_cmd.
    # Verbose mode streams the tool's own output and does not need a banner here,
    # since callers can log their own command banners to avoid duplication.
    if list_cmd:
        log(f"Running: {join_command(exe, args)}")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # Stream output when verbose; otherwise capture and return.
    if verbose:
        return _run_streaming(cmd, creationflags=creationflags, log=log)

    # Non-verbose: capture output and return.
    proc = subprocess.run(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
        check=True,
    )
    return proc.stdout


run_ffmpeg = partial(run, _FFMPEG)
run_ffprobe = partial(run, _FFPROBE)


def _get_version(run_func: Callable[[Sequence[str | Path]], str], name: str) -> str:
    """Return version string for an FF tool, raising if not available."""
    try:
        out = run_func(["-version"])
    except FileNotFoundError as e:  # pragma: no cover - system-dependent
        raise FileNotFoundError(f"{name} not found") from e
    except subprocess.CalledProcessError as e:  # pragma: no cover - unlikely
        raise RuntimeError(f"{name} failed: {e}") from e
    return out.splitlines()[0].strip()


def get_ffmpeg_version() -> str:
    """Return the ``ffmpeg`` version string."""
    return _get_version(run_ffmpeg, "ffmpeg")


def get_ffprobe_version() -> str:
    """Return the ``ffprobe`` version string."""
    return _get_version(run_ffprobe, "ffprobe")


def check_ffmpeg_version(ctx: RuntimeContext) -> str:
    """Return the ``ffmpeg`` version string using the shared cache."""
    version_obj = ctx.cache.get(_FFMPEG_VERSION_KEY)
    if isinstance(version_obj, str):
        return version_obj
    try:
        version = get_ffmpeg_version()
    except FileNotFoundError as e:  # pragma: no cover - system-dependent
        raise RuntimeError("ffmpeg not found") from e
    except subprocess.CalledProcessError as e:  # pragma: no cover - unlikely
        raise RuntimeError(f"ffmpeg failed: {e}") from e
    ctx.cache[_FFMPEG_VERSION_KEY] = version
    return version


def quote_arg(arg: str, *, force: bool = False) -> str:
    """Quote argument if needed."""
    if os.name == "nt":
        quoted = subprocess.list2cmdline([arg])
        if force and quoted == arg:
            return f'"{arg}"'
        return quoted
    quoted = shlex.quote(arg)
    if force and quoted == arg:
        return f"'{arg}'"
    return quoted


def join_command(exe: str | Path, args: Sequence[str | Path]) -> str:
    """Format a command for display."""
    parts = [str(exe), *[str(a) for a in args]]
    return " ".join(quote_arg(part, force=i > 0 and parts[i - 1] == _VIDEO_FILTER) for i, part in enumerate(parts))


def format_ffmpeg_cmd(args: Sequence[str | Path]) -> str:
    """Format an ``ffmpeg`` command for display."""
    return join_command(_FFMPEG, args)


__all__ = [
    "cache_key",
    "check_ffmpeg_version",
    "format_ffmpeg_cmd",
    "get_ffmpeg_version",
    "get_ffprobe_version",
    "join_command",
    "quote_arg",
    "run",
    "run_ffmpeg",
    "run_ffprobe",
]
