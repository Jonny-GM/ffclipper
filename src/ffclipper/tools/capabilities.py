"""FFmpeg capability detection helpers."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from ffclipper.models.types import Encoder, VideoCodec

from .cli import cache_key, run_ffmpeg

if TYPE_CHECKING:
    from ffclipper.models.context import RuntimeContext


def _ffmpeg_supports(ctx: RuntimeContext, args: list[str]) -> bool:
    """Run ``ffmpeg`` and cache whether the command succeeds."""
    key = cache_key(["ffmpeg", *args])
    cached = ctx.cache.get(key)
    if isinstance(cached, bool):
        return cached
    try:
        run_ffmpeg(args)
    except (FileNotFoundError, subprocess.CalledProcessError):
        ctx.cache[key] = False
        return False
    ctx.cache[key] = True
    return True


def _check_encoder(ctx: RuntimeContext, encoder: Encoder) -> bool:
    """Return True if ``encoder`` can encode a tiny sample."""
    args = [
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=200x200:d=0.1",
        "-frames:v",
        "1",
        "-an",
        "-c:v",
        encoder.ffmpeg_name,
        "-f",
        "null",
        "-",
    ]
    return _ffmpeg_supports(ctx, args)


def available_encoders(ctx: RuntimeContext) -> set[Encoder]:
    """Return the set of encoders that are usable on this system."""
    return {e for e in Encoder if e is not Encoder.AUTO and _check_encoder(ctx, e)}


PREFERRED_ENCODERS: dict[VideoCodec, tuple[Encoder, ...]] = {
    VideoCodec.H264: (Encoder.H264_NVENC, Encoder.X264),
    VideoCodec.HEVC: (Encoder.HEVC_NVENC, Encoder.X265),
    VideoCodec.AV1: (Encoder.SVT_AV1,),
}


def best_encoder_for(codec: VideoCodec, available: set[Encoder]) -> Encoder:
    """Select the most desirable encoder supporting ``codec``.

    Encoders are chosen in priority order defined by ``PREFERRED_ENCODERS``.

    Args:
        codec: Desired output video codec.
        available: Set of encoders supported on the current system.

    Returns:
        The highest-priority encoder for ``codec`` that is present in
        ``available``.

    Raises:
        ValueError: If no encoder supporting ``codec`` is available.

    """
    for enc in PREFERRED_ENCODERS.get(codec, ()):  # pragma: no branch - small
        if enc in available:
            return enc
    raise ValueError(f"No encoder available for codec '{codec.value}'")


def has_libplacebo(ctx: RuntimeContext) -> bool:
    """Return True if the ``libplacebo`` filter is available."""
    args = [
        "-init_hw_device",
        "vulkan",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=200x200:d=0.1",
        "-vf",
        "libplacebo",
        "-f",
        "null",
        "-",
    ]
    return _ffmpeg_supports(ctx, args)


__all__ = ["available_encoders", "best_encoder_for", "has_libplacebo"]
