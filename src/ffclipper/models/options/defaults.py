"""Default constants for option models."""

from __future__ import annotations

from ffclipper.models.types import Container, Encoder, Resolution

DEFAULT_AUDIO_KBPS = 128
DEFAULT_TARGET_SIZE_MB = 10
DEFAULT_RESOLUTION = Resolution.ORIGINAL
DEFAULT_ENCODER = Encoder.X264
DEFAULT_SUBTITLE_DELAY = 0
DEFAULT_CONTAINER = Container.MP4

__all__ = [
    "DEFAULT_AUDIO_KBPS",
    "DEFAULT_CONTAINER",
    "DEFAULT_ENCODER",
    "DEFAULT_RESOLUTION",
    "DEFAULT_SUBTITLE_DELAY",
    "DEFAULT_TARGET_SIZE_MB",
]
