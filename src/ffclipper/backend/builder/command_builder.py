"""Build FFmpeg command arguments from a clip plan."""

from ffclipper.models.plan import ClipPlan

from . import audio, mux, subs, trim, video
from .command_args import INPUT_FLAG, OVERWRITE_OUTPUT

# Overwrite output files without prompting and enable automatic hardware acceleration.
GLOBAL_FLAGS: tuple[str, ...] = (
    *OVERWRITE_OUTPUT,
    "-hwaccel",
    "auto",
)

# Toggle whether to use approximate stream copy trimming when copying streams.
# When ``True`` the copy trim uses fast arguments without keyframe probing.
FAST_STREAM_COPY: bool = True


def _trim_args(plan: ClipPlan) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return trim args before and after the input source."""
    if not plan.need_trim:
        return (), ()
    opts = plan.opts
    if opts.video.copy or opts.audio.copy:
        if FAST_STREAM_COPY:
            return trim.fast(plan)
        return trim.keyframe(plan), ()
    return trim.basic(plan), ()


def _video_args(plan: ClipPlan, pass_num: int | None, stats_id: str | None) -> tuple[str, ...]:
    """Return video stream arguments."""
    opts = plan.opts
    if opts.video.copy:
        return video.copy()
    return video.encode(plan, plan.effective_seconds, pass_num=pass_num, stats_id=stats_id)


def _audio_args(plan: ClipPlan, pass_num: int | None) -> tuple[str, ...]:
    """Return audio stream arguments."""
    opts = plan.opts
    if pass_num == 1 or not opts.audio.include:
        return audio.DISABLE
    if opts.audio.copy:
        return audio.copy()
    return audio.encode(opts)


def build_command(
    plan: ClipPlan, *, pass_num: int | None = None, stats_id: str | None = None
) -> tuple[tuple[str, ...], str]:
    """Return FFmpeg command and expected output path."""
    opts = plan.opts
    args = GLOBAL_FLAGS + video.tonemap_hw_device(plan)
    pre_trim, post_trim = _trim_args(plan)
    args = (
        args
        + pre_trim
        + INPUT_FLAG
        + (str(opts.source),)
        + post_trim
        + _video_args(plan, pass_num, stats_id)
        + _audio_args(plan, pass_num)
    )
    passthrough = (opts.video.copy or opts.audio.copy) and (not FAST_STREAM_COPY or not plan.need_trim)
    mux_args = (
        ("-f", "mp4") if pass_num == 1 else mux.build(plan, passthrough=passthrough)
    )  # Two-pass first run discards output; MP4 muxer is required for x264/x265
    args = args + subs.build(plan) + mux_args + (str(plan.output_path),)
    return args, str(plan.output_path)


__all__ = ["GLOBAL_FLAGS", "build_command"]
