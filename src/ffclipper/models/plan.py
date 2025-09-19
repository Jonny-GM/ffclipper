"""Transcode planning models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ffclipper.tools import available_encoders, best_encoder_for, check_ffmpeg_version, probe

from .options import DEFAULT_CONTAINER, DEFAULT_SUBTITLE_DELAY, Options, compute_time_bounds
from .types import AudioCodec, Container, Encoder, SubtitleBurnMethod, VideoCodec

CLIP_SUFFIX = "_clip"  #: Suffix appended to default output filenames.
AUTO_EXTRACT_RATIO_THRESHOLD = 0.25  #: Max clip/source duration ratio for auto subtitle extraction.

if TYPE_CHECKING:
    from .context import RuntimeContext


@dataclass(slots=True)
class ClipPlan:
    """Execution plan resolved from user options."""

    opts: Options
    ctx: RuntimeContext
    output_path: Path
    start_ms: int
    duration_ms: int | None
    video_duration_sec: float
    need_trim: bool
    effective_seconds: float
    burn_subtitles: int | None
    copy_subtitles: bool
    subtitle_delay: int | None
    subtitle_burn_method: SubtitleBurnMethod | None
    need_tonemap: bool
    video_codec: VideoCodec | None = None
    audio_codec: AudioCodec | None = None

    @classmethod
    def from_options(cls, opts: Options, ctx: RuntimeContext) -> ClipPlan:
        """Create a plan from raw options."""
        _ensure_tools(ctx, opts)

        src_val = str(opts.source)
        video_duration = _probe_duration(ctx, src_val)
        start_ms, duration_ms = compute_time_bounds(opts, video_duration)
        need_trim = any([opts.time.start_ms, opts.time.end_ms, opts.time.duration_ms])
        if not need_trim:
            duration_ms = None
        effective_seconds = duration_ms / 1000.0 if duration_ms is not None else video_duration

        container = opts.container if opts.container is not None else DEFAULT_CONTAINER
        output_path = derive_output_path(src_val, opts.output, container)

        video_codec, audio_codec = _validate_container(opts, ctx)

        burn = opts.subtitles.burn if opts.should_burn_subtitles() else None
        method = opts.subtitles.burn_method
        delay = opts.subtitles.delay
        if burn is not None:
            if method is None or method is SubtitleBurnMethod.AUTO:
                ratio = effective_seconds / video_duration if video_duration else 1
                method = (
                    SubtitleBurnMethod.EXTRACT if ratio <= AUTO_EXTRACT_RATIO_THRESHOLD else SubtitleBurnMethod.INLINE
                )
            if delay is None:
                delay = DEFAULT_SUBTITLE_DELAY
        else:
            method = None
            delay = None
        copy_subs = opts.should_copy_subtitles()
        tonemap = _should_tonemap(ctx, opts)

        return cls(
            opts=opts,
            ctx=ctx,
            output_path=output_path,
            start_ms=start_ms,
            duration_ms=duration_ms,
            video_duration_sec=video_duration,
            need_trim=need_trim,
            effective_seconds=effective_seconds,
            burn_subtitles=burn,
            copy_subtitles=copy_subs,
            subtitle_delay=delay,
            subtitle_burn_method=method,
            need_tonemap=tonemap,
            video_codec=video_codec,
            audio_codec=audio_codec,
        )


def _ensure_tools(ctx: RuntimeContext, opts: Options) -> None:
    """Validate that ffmpeg, ffprobe, and the selected encoder are available."""
    try:
        check_ffmpeg_version(ctx)
        probe.check_version(ctx)
    except (OSError, RuntimeError) as e:  # pragma: no cover - environment dependent
        raise ValueError(str(e)) from e

    if not opts.video.copy:
        avail = available_encoders(ctx)
        if opts.video.encoder in {None, Encoder.AUTO}:
            if opts.video.codec is None:
                raise ValueError("codec not set")
            opts.video.encoder = best_encoder_for(opts.video.codec, avail)
        elif opts.video.encoder not in avail:
            raise ValueError(f"Video encoder '{opts.video.encoder}' not available")
        encoder = opts.video.encoder
        if encoder is None:
            raise ValueError("encoder not set")
        if opts.video.codec is None:
            opts.video.codec = encoder.codec


def _probe_duration(ctx: RuntimeContext, source: str) -> float:
    """Return the duration of ``source`` in seconds."""
    dur = probe.get_video_duration_sec(ctx, source)
    if dur is None:
        raise ValueError(f"Could not read video duration from: {source}")
    return dur


def _validate_container(opts: Options, ctx: RuntimeContext) -> tuple[VideoCodec | None, AudioCodec | None]:
    """Resolve probed codecs and record output codecs.

    Behavior for stream copy:
    - When ``video.copy`` or ``audio.copy`` is enabled, do not enforce
      container/enum compatibility. We attempt pass-through regardless of the
      probed codec. Unknown codecs are represented as ``None`` in the returned
      tuple, and downstream components should avoid codec-specific tagging in
      that case.

    Behavior for encoding:
    - Rely on ``Options`` validators to ensure encoder/container compatibility
      and simply record the encoder's output codec.
    """
    video_codec: VideoCodec | None
    if opts.video.copy:
        # Probe and coerce to our enum if possible; otherwise leave as None and
        # allow ffmpeg to attempt pass-through regardless of container.
        info = probe.get_video_codec(ctx, str(opts.source))
        codec_name = info.codec if info else None
        try:
            video_codec = VideoCodec(codec_name) if codec_name else None
        except ValueError:
            video_codec = None
    else:
        if opts.video.encoder is None:
            raise ValueError("encoder not set")
        # Encoder/container compatibility is validated by Options; just record the codec.
        video_codec = opts.video.encoder.codec

    audio_codec: AudioCodec | None = None
    if opts.audio.include:
        if opts.audio.copy:
            # Probe and coerce to our enum if possible; otherwise leave as None
            # and allow ffmpeg to attempt pass-through regardless of container.
            info = probe.get_audio_codec(ctx, str(opts.source))
            codec_name = info.codec if info else None
            try:
                audio_codec = AudioCodec(codec_name) if codec_name else None
            except ValueError:
                audio_codec = None
        else:
            # Choose container-appropriate codec when encoding audio.
            audio_codec = AudioCodec.OPUS if opts.container == Container.WEBM else AudioCodec.AAC

    return video_codec, audio_codec


def _should_tonemap(ctx: RuntimeContext, opts: Options) -> bool:
    """Determine if tonemapping is required for the planned conversion."""
    if opts.video.copy:
        return False
    encoder = opts.video.encoder
    if encoder is None:
        raise ValueError("encoder not set")
    if encoder.codec.supports_hdr:
        return False
    info = probe.get_video_color_info(ctx, str(opts.source))
    return bool(info and info.transfer and info.transfer.is_hdr)


def derive_output_path(source: str | Path, output: Path | None, container: Container) -> Path:
    """Derive the resolved output path based on source, explicit output, and container.

    Mirrors the filename derivation used in ``ClipPlan.from_options`` without
    performing any probing or external validation.
    """
    if output:
        p = Path(output)
        if not p.suffix:
            p = p.with_suffix(f".{container.value}")
        return p.expanduser().absolute()

    src_val = str(source)
    parsed = urlparse(src_val)
    is_url = parsed.scheme in {"http", "https"}
    if is_url:
        name = Path(parsed.path).name
        if not name:
            # Fallback: keep as current working directory with generic name
            # The GUI will avoid deriving in this case; keep logic safe here.
            raise ValueError("Cannot derive output filename from URL; please provide --output")
        p = Path.cwd() / f"{Path(name).stem}{CLIP_SUFFIX}.{container.value}"
        return p.expanduser().absolute()

    src = Path(src_val).expanduser()
    p = src.parent / f"{src.stem}{CLIP_SUFFIX}.{container.value}"
    return p.expanduser().absolute()
