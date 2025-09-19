"""Video stream argument helpers."""

from collections import defaultdict

from ffclipper.models import Encoder
from ffclipper.models.plan import ClipPlan
from ffclipper.tools import probe
from ffclipper.tools.capabilities import has_libplacebo
from ffclipper.tools.helpers import emit_status

from . import subs
from .stream_args import bitrate_flag, codec_flag, copy_stream, map_spec

MAP: tuple[str, ...] = map_spec("v")  #: Select the first video stream from the input.
CODEC: tuple[str, ...] = codec_flag("v")  #: Video codec flag used to specify encoder or copy mode.
COPY: tuple[str, ...] = copy_stream("v")  #: Pass video stream through without re-encoding.
FILTER: tuple[str, ...] = ("-vf",)  #: Filter graph flag for video processing steps.
BITRATE: tuple[str, ...] = bitrate_flag("v")  #: Target average video bitrate.
MAXRATE: tuple[str, ...] = ("-maxrate",)  #: Peak video bitrate to constrain rate control.
BUFSIZE: tuple[str, ...] = ("-bufsize",)  #: Rate control buffer size.
RC_VBR: tuple[str, ...] = ("-rc:v", "vbr")  #: Variable bitrate control mode.
TUNE_HQ: tuple[str, ...] = ("-tune:v", "hq")  #: High quality tuning.
MULTIPASS_FULLRES: tuple[str, ...] = ("-multipass", "fullres")  #: Full-resolution multipass mode.
SPATIAL_AQ: tuple[str, ...] = ("-spatial-aq", "1")  #: Enable spatial adaptive quantization.
TEMPORAL_AQ: tuple[str, ...] = ("-temporal-aq", "1")  #: Enable temporal adaptive quantization.
AQ_STRENGTH: tuple[str, ...] = ("-aq-strength", "8")  #: Strength of adaptive quantization.
RC_LOOKAHEAD: tuple[str, ...] = ("-rc-lookahead", "20")  #: Frames for rate control lookahead.
PRESET_SLOW: tuple[str, ...] = ("-preset", "slow")  #: Default preset for software encoding.
PRESET_P6: tuple[str, ...] = ("-preset", "p6")  #: Quality preset for NVENC.
PROFILE_HIGH: tuple[str, ...] = ("-profile:v", "high")  #: High profile for broad compatibility.
PROFILE_MAIN: tuple[str, ...] = ("-profile:v", "main")  #: Main profile for HEVC compatibility.
B_REF_MODE: tuple[str, ...] = ("-b_ref_mode", "middle")  #: Reference mode for B-frames.
PIX_FMT: tuple[str, ...] = ("-pix_fmt", "yuv420p")  #: Pixel format for broad player compatibility.
PASS: tuple[str, ...] = ("-pass",)  #: Two-pass flag.
PASSLOGFILE: tuple[str, ...] = ("-passlogfile",)  #: Pass log file base name.
X265_PARAMS: tuple[str, ...] = ("-x265-params",)  #: x265 parameter flag.
VBV_PREFIX: str = "vbv-"  #: Prefix for x265 VBV parameters.
TONEMAP_ZSCALE: str = (
    "zscale=t=linear:npl=100,"
    "tonemap=tonemap=hable,"
    "zscale=t=bt709:m=bt709:r=tv"
)  #: Filter chain for HDR to SDR tonemapping via ``zscale``.
TONEMAP_LIBPLACEBO: str = (
    "libplacebo=tonemapping=bt.2446a:"
    "colorspace=bt709:color_trc=bt709:color_primaries=bt709"
)  #: Filter chain for HDR to SDR tonemapping via ``libplacebo``.

COMMON_FLAGS: tuple[str, ...] = PIX_FMT  #: Flags applied to all encoders.
ENCODER_FLAGS: dict[Encoder, tuple[str, ...]] = {
    Encoder.X264: PRESET_SLOW + PROFILE_HIGH,
    Encoder.X265: PRESET_SLOW,
    Encoder.H264_NVENC: (
        PRESET_P6
        + TUNE_HQ
        + RC_VBR
        + MULTIPASS_FULLRES
        + RC_LOOKAHEAD
        + SPATIAL_AQ
        + TEMPORAL_AQ
        + AQ_STRENGTH
        + B_REF_MODE
        + PROFILE_HIGH
    ),
    Encoder.HEVC_NVENC: (
        PRESET_P6
        + TUNE_HQ
        + RC_VBR
        + MULTIPASS_FULLRES
        + RC_LOOKAHEAD
        + SPATIAL_AQ
        + TEMPORAL_AQ
        + AQ_STRENGTH
        + B_REF_MODE
        + PROFILE_MAIN
    ),
}  #: Encoder-specific quality flags.

MAXRATE_MULTIPLIER: float = 1.0  #: Ratio of peak to average bitrate.
BUFSIZE_MULTIPLIER: int = 2  #: Buffer size relative to the average bitrate.
# Reserve factor by encoder for container overhead; defaults to 5%.
RESERVE_BY_ENCODER: defaultdict[Encoder, float] = defaultdict(
    lambda: 0.95,
    {
        Encoder.H264_NVENC: 0.85,
        Encoder.HEVC_NVENC: 0.85,
        Encoder.X264: 0.97,
        Encoder.X265: 0.97,
    },
)
TONEMAP_HW_DEVICE: tuple[str, ...] = (
    "-init_hw_device",
    "vulkan",
)  #: Vulkan hardware device initialization for libplacebo.


def _vbv_components(flag: tuple[str, ...], value: int) -> tuple[tuple[str, ...], str]:
    """Return CLI args and flag name for VBV settings."""
    flag_name = flag[0].removeprefix("-")
    return (*flag, f"{value}k"), flag_name


def _audio_budget_kbps(plan: ClipPlan) -> int:
    """Estimate audio bitrate to budget against the target size.

    When copying audio, we probe the source average audio bitrate. When
    encoding audio, we use the configured ``opts.audio.kbps``. If audio is
    excluded, the budget is ``0``.
    """
    opts = plan.opts
    if not opts.audio.include:
        return 0
    if opts.audio.copy:
        info = probe.get_audio_bitrate(plan.ctx, str(opts.source))
        return info.bitrate if info and isinstance(info.bitrate, int) else 0
    return opts.audio.kbps or 0


def _raw_bitrate(plan: ClipPlan, secs: float, reserve_factor: float) -> int:
    """Compute raw video bitrate budget in kbps (can be <= 0)."""
    if secs <= 0:
        raise ValueError("Duration must be greater than 0")
    target_size = plan.opts.target_size or 0
    max_size = int(target_size * 1024 * 1024 * reserve_factor)
    audio_kbps = _audio_budget_kbps(plan)
    return int((max_size * 8) / (secs * 1000) - audio_kbps)


def tonemap_hw_device(plan: ClipPlan) -> tuple[str, ...]:
    """Return hardware device initialization args for tonemapping."""
    if plan.need_tonemap and has_libplacebo(plan.ctx):
        return TONEMAP_HW_DEVICE
    return ()


def filters(plan: ClipPlan) -> tuple[str, ...]:
    """Return video filter expressions for subtitles or scaling.

    When subtitle burn-in is requested, the filter from
    :func:`ffclipper.backend.builder.subs.burn_filter` is included. That filter
    relies on :func:`ffclipper.backend.builder.subs.prepare_burn` having run
    earlier to determine whether to reference a temporary subtitle file or the
    source stream.
    """
    filters: list[str] = []
    if plan.need_tonemap:
        if has_libplacebo(plan.ctx):
            filters.append(TONEMAP_LIBPLACEBO)
        else:
            filters.append(TONEMAP_ZSCALE)
    if plan.burn_subtitles is not None:
        filters.append(subs.burn_filter(plan))
    if plan.opts.video.resolution and plan.opts.video.resolution.height is not None:
        filters.append(f"scale=-2:{plan.opts.video.resolution.height}")
    return tuple(filters)


def encode(plan: ClipPlan, secs: float, *, pass_num: int | None = None, stats_id: str | None = None) -> tuple[str, ...]:
    """Return args to encode video according to ``plan``."""
    opts = plan.opts
    encoder = opts.video.encoder
    if encoder is None:
        raise ValueError("encoder not set")
    reserve = RESERVE_BY_ENCODER[encoder]
    raw_kbps = _raw_bitrate(plan, secs, reserve)
    if opts.target_size is not None and raw_kbps <= 0:
        # Warn to the status callback (if any) and raise a clear error early.
        audio_kbps = _audio_budget_kbps(plan)
        msg = (
            "Target size leaves no bitrate budget for video "
            f"(audio ~= {audio_kbps} kbps over {secs:.2f}s, target ~= {opts.target_size} MB). "
            "Increase --target-size, lower --audio-kbps, or avoid audio copy."
        )
        emit_status(msg, status_callback=plan.ctx.status_callback)
        raise ValueError("No video bitrate budget given current target size and audio settings")
    kbps = max(100, raw_kbps)
    maxrate = int(kbps * MAXRATE_MULTIPLIER)
    bufsize = int(kbps * BUFSIZE_MULTIPLIER)
    maxrate_arg, maxrate_flag = _vbv_components(MAXRATE, maxrate)
    bufsize_arg, bufsize_flag = _vbv_components(BUFSIZE, bufsize)
    args = MAP + CODEC + (encoder.ffmpeg_name,)
    args = args + BITRATE + (f"{kbps}k",)
    if encoder != Encoder.X265:
        args = args + maxrate_arg + bufsize_arg
    args = args + ENCODER_FLAGS.get(encoder, ())
    args = args + COMMON_FLAGS
    if encoder in {Encoder.X264, Encoder.X265}:
        if pass_num is None:
            pass_num = 2
        if stats_id is None:
            stats_id = "ffclipper"
        if encoder == Encoder.X264:
            args = args + PASS + (str(pass_num),) + PASSLOGFILE + (f"{stats_id}.x264",)
        else:
            args = (
                args
                + X265_PARAMS
                + (
                    f"pass={pass_num}:stats={stats_id}.x265:"
                    f"{VBV_PREFIX}{maxrate_flag}={maxrate}:"
                    f"{VBV_PREFIX}{bufsize_flag}={bufsize}",
                )
            )
    if flt := filters(plan):
        args = args + FILTER + (",".join(flt),)
    return args


def copy() -> tuple[str, ...]:
    """Return args to stream copy the first video track."""
    return MAP + COPY
