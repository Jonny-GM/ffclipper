"""Container flags."""

from ffclipper.models import Container, VideoCodec
from ffclipper.models.plan import ClipPlan

FASTSTART: tuple[str, ...] = ("-movflags", "+faststart")  #: Optimize MP4 files for streaming.
TAG_AVC1: tuple[str, ...] = ("-tag:v", "avc1")  #: Tag H.264 streams for QuickTime compatibility.
TAG_HVC1: tuple[str, ...] = ("-tag:v", "hvc1")  #: Tag HEVC streams for QuickTime compatibility.
PASSTHROUGH: tuple[str, ...] = (
    # "-shortest",  # Stop muxing when the shortest stream ends. Disabled for now.
    "-avoid_negative_ts",  # Avoid negative timestamps by shifting.
    "make_zero",  # Shift timestamps so first is zero.
    "-muxpreload",  # Reduce initial demuxer delay.
    "0",
    "-muxdelay",  # Reduce internal muxer buffering.
    "0",
    "-copytb",  # Use input timebase when stream copying.
    "1",
)  #: Flags to keep timestamps stable when copying streams.


DROP_CHAPTERS: tuple[str, ...] = (
    "-map_chapters",
    "-1",
)  #: Remove inherited chapters when trimming to avoid incorrect metadata.


def build(plan: ClipPlan, *, passthrough: bool) -> tuple[str, ...]:
    """Return container muxing args."""
    args: tuple[str, ...] = ()
    opts = plan.opts
    if opts.container == Container.MP4:
        args = args + FASTSTART
        # Determine video codec tag when known. When copying and the probed
        # codec is unknown, skip tagging and let ffmpeg attempt pass-through.
        vid: str | None = None
        if opts.video.copy:
            if plan.video_codec:
                vid = plan.video_codec.value
        else:
            encoder = opts.video.encoder
            if encoder is None:
                raise ValueError("encoder not set")
            vid = encoder.codec.value
        if vid == VideoCodec.H264.value:
            args = args + TAG_AVC1
        elif vid in {VideoCodec.HEVC.value, "h265"}:
            args = args + TAG_HVC1
    if plan.need_trim:
        args = args + DROP_CHAPTERS
    if passthrough:
        args = args + PASSTHROUGH
    return args
