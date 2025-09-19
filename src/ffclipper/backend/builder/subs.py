"""Subtitle utilities and flags."""

from pathlib import Path
from tempfile import NamedTemporaryFile

from ffclipper.models import Container, SubtitleBurnMethod
from ffclipper.models.context import RuntimeContext
from ffclipper.models.plan import ClipPlan
from ffclipper.tools import escape_filter_path_for_windows, format_time

from .command_args import INPUT_FLAG, OVERWRITE_OUTPUT
from .stream_args import codec_flag, copy_stream, map_spec

MAP_SUB: tuple[str, ...] = map_spec("s", index=None, optional=True)  #: Select subtitles if present.
SUB_CODEC: tuple[str, ...] = codec_flag("s")  #: Subtitle codec flag.
COPY_SUB: tuple[str, ...] = copy_stream("s")  #: Pass subtitle stream through.
MOV_TEXT: tuple[str, ...] = (*SUB_CODEC, "mov_text")  #: Convert subtitles to mov_text for MP4.

BURN_FILTER = "subtitles"  #: FFmpeg subtitles filter name.


def build(plan: ClipPlan) -> tuple[str, ...]:
    """Return muxing args when copying subtitles for the final container."""
    if not plan.copy_subtitles:
        return ()
    mov_text = plan.opts.container == Container.MP4
    return MAP_SUB + (MOV_TEXT if mov_text else COPY_SUB)


def burn_filter(plan: ClipPlan) -> str:
    """Return subtitles filter for burn-in.

    When using extracted subtitles, ``prepare_burn`` must be invoked beforehand
    so the temporary subtitle path stored on the plan's context can be
    consulted here. If extraction is configured but the file has not been
    prepared, a :class:`FileNotFoundError` is raised to signal misuse. If no
    extraction has taken place, the filter targets the stream index from
    ``opts`` on the original source.

    Raises:
        FileNotFoundError: If ``subtitle_burn_method`` requires extraction and
            the expected subtitle file is missing.

    """
    path = plan.ctx.burn_subtitle_path
    if plan.subtitle_burn_method is SubtitleBurnMethod.EXTRACT and (not path or not path.exists()):
        raise FileNotFoundError(
            "prepare_burn must be called before burn_filter when using extracted subtitles",
        )
    fp_src = str(path) if path else str(plan.opts.source)
    fp = escape_filter_path_for_windows(fp_src)
    if path:
        return f"{BURN_FILTER}='{fp}'"
    return f"{BURN_FILTER}='{fp}':si={plan.burn_subtitles}"


def prepare_burn(plan: ClipPlan) -> tuple[str, ...]:
    """Return args to pre-extract the burn-in subtitle clip.

    The returned argument list runs a lightweight ``ffmpeg`` command to write
    the selected subtitle stream to a temporary ``.srt`` file. The path is
    stored on ``plan.ctx`` so that :func:`burn_filter` can reference the
    extracted subtitles during the main encode. A pre-input seek avoids scanning
    the full file, then a zero-offset seek after the input drops any cues before
    the clip. ``-itsoffset`` shifts subtitle timing when a delay is requested.
    """
    with NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        temp_sub = Path(tmp.name)
    # Keep the extracted subtitle file on the runtime context for later use/cleanup.
    plan.ctx.burn_subtitle_path = temp_sub
    offset = (
        (
            "-itsoffset",
            f"{plan.subtitle_delay / 1000:.3f}",
        )
        if plan.subtitle_delay
        else ()
    )
    pre_trim: list[str] = []
    post_trim: list[str] = []
    if plan.start_ms:
        pre_trim += ["-ss", format_time(plan.start_ms / 1000.0)]
        post_trim += ["-ss", "0"]
    if plan.duration_ms:
        post_trim += ["-t", format_time(plan.duration_ms / 1000.0)]
    return (
        OVERWRITE_OUTPUT
        + offset
        + tuple(pre_trim)
        + INPUT_FLAG
        + (str(plan.opts.source),)
        + tuple(post_trim)
        + map_spec("s", index=plan.burn_subtitles)
        + COPY_SUB
        + (str(temp_sub),)
    )


def cleanup_burn(ctx: RuntimeContext) -> None:
    """Remove temporary burn-in subtitle file and reset path."""
    path = ctx.burn_subtitle_path
    if path:
        path.unlink(missing_ok=True)
        ctx.burn_subtitle_path = None
