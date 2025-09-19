"""Build and execute FFmpeg commands."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import uuid
from contextlib import suppress
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from cyclopts import Parameter

from ffclipper.models import ClipPlan, Encoder, Options, RuntimeContext, SubtitleBurnMethod
from ffclipper.models.verbosity import Verbosity
from ffclipper.tools import format_ffmpeg_cmd, run_ffmpeg
from ffclipper.tools.helpers import emit_status, format_action_label, maybe_log_command

from .builder import build_command, subs

if TYPE_CHECKING:
    from collections.abc import Callable
else:
    from collections import abc

    Callable = abc.Callable

CONVERSION_FAILED = "Conversion failed"

logger = logging.getLogger(__name__)

STATS_FILES = {
    Encoder.X264: [".x264-0.log", ".x264-0.log.mbtree"],
    Encoder.X265: [".x265"],
}


def _cleanup_pass_stats(stats_id: str, encoder: Encoder) -> None:
    """Remove temporary two-pass stats files."""
    for suffix in STATS_FILES.get(encoder, []):
        Path(f"{stats_id}{suffix}").unlink(missing_ok=True)


def _ensure_output_parent(
    path: Path,
    verbosity: Verbosity,
    status_callback: Callable[[str], None] | None,
) -> None:
    """Create the output parent directory if missing.

    Raises:
        OSError: If directory creation fails.

    """
    parent = path.parent
    if parent.exists():
        if not parent.is_dir():
            raise OSError(f"{CONVERSION_FAILED}: Output directory parent is not a directory: {parent}")
        return
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:  # pragma: no cover - filesystem errors depend on env
        raise OSError(f"{CONVERSION_FAILED}: {e}") from e
    if verbosity > Verbosity.QUIET:
        emit_status(f"Created output directory: {parent}", status_callback=status_callback)


@dataclass
class FFmpegResult:
    """Result of an FFmpeg execution."""

    success: bool
    error: str = ""
    output: str | None = None


def _maybe_extract_subtitles(
    plan: ClipPlan,
    opts: Options,
    commands: list[tuple[str, ...]],
    status_callback: Callable[[str], None] | None,
) -> tuple[ClipPlan, FFmpegResult | None]:
    """Extract subtitles for burn-in when requested."""
    if plan.burn_subtitles is None or plan.subtitle_burn_method != SubtitleBurnMethod.EXTRACT:
        return plan, None
    extract_args = subs.prepare_burn(plan)
    commands.append(extract_args)
    if opts.runtime.dry_run:
        banner = f"{format_action_label(dry_run=True)}: {format_ffmpeg_cmd(extract_args)}"
        maybe_log_command(
            verbosity=opts.runtime.verbosity,
            dry_run=True,
            status_callback=status_callback,
            banner=banner,
        )
        return plan, None
    try:
        run_ffmpeg(
            extract_args,
            verbose=opts.runtime.verbosity >= Verbosity.OUTPUT,
            status_callback=status_callback,
            list_cmd=opts.runtime.verbosity >= Verbosity.COMMANDS,
        )
    except subprocess.CalledProcessError as e:
        return plan, FFmpegResult(success=False, error=f"{CONVERSION_FAILED}: {e.stdout or e}")
    sub_path = plan.ctx.burn_subtitle_path
    if sub_path and sub_path.stat().st_size == 0:
        emit_status(
            "Subtitle track appears empty in this time range, skipping subtitle burn-in...",
            status_callback=status_callback,
        )
        sub_path.unlink(missing_ok=True)
        plan.ctx.burn_subtitle_path = None
        plan = replace(
            plan,
            burn_subtitles=None,
            copy_subtitles=plan.opts.should_copy_subtitles(),
        )
    return plan, None


def _run_command(
    args: tuple[str, ...],
    output: str,
    opts: Options,
    commands: list[tuple[str, ...]],
    status_callback: Callable[[str], None] | None,
) -> FFmpegResult:
    """Run or list an FFmpeg command based on runtime options."""
    commands.append(args)
    if opts.runtime.dry_run:
        banner = f"{format_action_label(dry_run=True)}: {format_ffmpeg_cmd(args)}"
        maybe_log_command(
            verbosity=opts.runtime.verbosity,
            dry_run=True,
            status_callback=status_callback,
            banner=banner,
        )
        return FFmpegResult(success=True, output=output)
    return execute_ffmpeg(
        args,
        output,
        verbose=opts.runtime.verbosity >= Verbosity.OUTPUT,
        list_cmd=opts.runtime.verbosity >= Verbosity.COMMANDS,
        status_callback=status_callback,
    )


def run_conversion(
    opts: Options,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[tuple[tuple[str, ...], ...], FFmpegResult]:
    """Build and optionally execute an FFmpeg command from options."""
    with RuntimeContext(
        verbosity=opts.runtime.verbosity,
        dry_run=opts.runtime.dry_run,
        status_callback=status_callback,
    ) as runtime:
        plan = ClipPlan.from_options(opts, runtime)
        try:
            _ensure_output_parent(plan.output_path, opts.runtime.verbosity, status_callback)
        except OSError as e:
            return (), FFmpegResult(success=False, error=str(e))
        commands: list[tuple[str, ...]] = []
        stats_id: str | None = None
        try:
            plan, err_result = _maybe_extract_subtitles(plan, opts, commands, status_callback)
            if err_result is not None:
                args, _ = build_command(plan)
                return (*tuple(commands), args), err_result
            two_pass = plan.opts.video.encoder in {Encoder.X264, Encoder.X265} and not plan.opts.video.copy
            stats_id = uuid.uuid4().hex if two_pass else None
            if two_pass:
                pass1_args, _ = build_command(plan, pass_num=1, stats_id=stats_id)
                pass1_args = (*pass1_args[:-1], os.devnull)
                result = _run_command(
                    pass1_args,
                    os.devnull,
                    opts,
                    commands,
                    status_callback,
                )
                if not result.success:
                    return tuple(commands), result
            args, output = build_command(plan, pass_num=2 if two_pass else None, stats_id=stats_id)
            result = _run_command(args, output, opts, commands, status_callback)
            if result.success and result.output:
                emit_status(str(Path(result.output).absolute()), status_callback=status_callback)
                # Only open the directory when not in dry-run mode
                if opts.runtime.open_dir and not opts.runtime.dry_run:
                    open_directory(result.output)
            return tuple(commands), result
        finally:
            subs.cleanup_burn(runtime)
            if stats_id and not opts.runtime.dry_run:
                _cleanup_pass_stats(stats_id, plan.opts.video.encoder)


def execute_ffmpeg(
    args: tuple[str, ...],
    output: str,
    *,
    verbose: bool = False,
    list_cmd: bool = False,
    status_callback: Callable[[str], None] | None = None,
) -> FFmpegResult:
    """Execute an FFmpeg command and return result."""
    try:
        run_ffmpeg(args, verbose=verbose, status_callback=status_callback, list_cmd=list_cmd)
    except (subprocess.CalledProcessError, OSError) as e:
        return FFmpegResult(success=False, error=f"{CONVERSION_FAILED}: {e!s}")
    return FFmpegResult(success=True, output=output)


def open_directory(output: str) -> None:
    """Reveal ``output`` in the system file manager.

    On Windows and macOS the file itself is selected.  Linux falls back to
    opening the containing directory.  Any errors are suppressed silently.
    """
    path = Path(output).absolute()
    if sys.platform == "win32":
        cmd = shutil.which("explorer")
        if cmd:
            with suppress(OSError):
                subprocess.run([cmd, "/select,", str(path)], check=False)  # noqa: S603
        return
    if sys.platform == "darwin":
        cmd = shutil.which("open")
        if cmd:
            with suppress(OSError):
                subprocess.run([cmd, "-R", str(path)], check=False)  # noqa: S603
        return
    cmd = shutil.which("xdg-open")
    if cmd:
        with suppress(OSError):
            subprocess.run([cmd, str(path.parent)], check=False)  # noqa: S603


def ffclipper(
    opts: Options,
    status_callback: Annotated[Callable[[str], None] | None, Parameter(show=False)] = None,  # type: ignore[call-arg]
) -> int:
    """Create a clip from a source video."""
    status_func = print if status_callback is None else status_callback
    _, result = run_conversion(opts, status_callback=status_func)
    if not result.success:
        err_func = partial(print, file=sys.stderr, flush=True) if status_callback is None else status_callback
        err_func(result.error)
        return 1
    return 0
