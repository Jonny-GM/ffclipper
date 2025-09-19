"""Time range argument helpers."""

from ffclipper.models.plan import ClipPlan
from ffclipper.models.verbosity import Verbosity
from ffclipper.tools import format_time, probe
from ffclipper.tools.helpers import emit_status

START: tuple[str, ...] = ("-ss",)  #: Seek to this start timestamp before decoding.
END: tuple[str, ...] = ("-to",)  #: End timestamp for trimming in decoding mode.
DURATION: tuple[str, ...] = ("-t",)  #: Duration to process from the start position.
SEEK2ANY: tuple[str, ...] = ("-seek2any", "0")  #: Restrict seeks to keyframes for copy mode.
COPYTS: tuple[str, ...] = ("-copyts",)  #: Preserve input timestamps when copying streams.


def basic(plan: ClipPlan) -> tuple[str, ...]:
    """Return decode-path trim args using ``-ss`` and ``-t``."""
    args: list[str] = []
    if plan.start_ms:
        args += [*START, format_time(plan.start_ms / 1000.0)]
    if plan.duration_ms:
        args += [*DURATION, format_time(plan.duration_ms / 1000.0)]
    return tuple(args)


def keyframe(plan: ClipPlan) -> tuple[str, ...]:
    """Return keyframe-aligned trim args for stream copy mode."""
    start_s = plan.start_ms / 1000.0
    end_s = start_s + (plan.duration_ms / 1000.0) if plan.duration_ms is not None else plan.video_duration_sec

    start_kf, end_kf = probe.snap_window_copy_bounds(plan.ctx, str(plan.opts.source), start_s, end_s)

    if plan.opts.runtime.verbosity >= Verbosity.COMMANDS:
        emit_status(
            f"Original request: {start_s:.3f}s to {end_s:.3f}s",
            status_callback=plan.ctx.status_callback,
        )
        emit_status(
            f"Snapped to keyframes: {start_kf:.3f}s to {end_kf:.3f}s",
            status_callback=plan.ctx.status_callback,
        )

    return (
        SEEK2ANY
        + START
        + (format_time(start_kf, places=3, mode="floor"),)
        + END
        + (format_time(end_kf, places=3, mode="ceil"),)
        + COPYTS
    )


def fast(plan: ClipPlan) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return trim args for stream copy without keyframe probing."""
    pre: list[str] = []
    post: list[str] = []
    if plan.start_ms:
        pre += ["-noaccurate_seek", *START, format_time(plan.start_ms / 1000.0)]
    if plan.duration_ms and plan.duration_ms > 0:
        post += [*DURATION, format_time(plan.duration_ms / 1000.0)]
    return tuple(pre), tuple(post)
