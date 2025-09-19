"""Options package exports."""

# ruff: noqa: E402  (imports follow early warning filter by design)

from __future__ import annotations

import warnings

from ffclipper.models.verbosity import Verbosity

# Silence pydantic shadowing warning for fields named "copy" in submodels
warnings.filterwarnings(
    "ignore",
    r'Field name "copy" in "(AudioOptions|VideoOptions)" shadows an attribute in parent "BaseModel"',
    UserWarning,
)

from .audio import AudioOptions
from .defaults import (
    DEFAULT_AUDIO_KBPS,
    DEFAULT_CONTAINER,
    DEFAULT_ENCODER,
    DEFAULT_RESOLUTION,
    DEFAULT_SUBTITLE_DELAY,
    DEFAULT_TARGET_SIZE_MB,
)
from .options import Options
from .runtime import RuntimeOptions
from .subtitles import SubtitlesOptions
from .time import TimeOptions, compute_time_bounds
from .video import VideoOptions

__all__ = [
    "DEFAULT_AUDIO_KBPS",
    "DEFAULT_CONTAINER",
    "DEFAULT_ENCODER",
    "DEFAULT_RESOLUTION",
    "DEFAULT_SUBTITLE_DELAY",
    "DEFAULT_TARGET_SIZE_MB",
    "AudioOptions",
    "Options",
    "RuntimeOptions",
    "SubtitlesOptions",
    "TimeOptions",
    "Verbosity",
    "VideoOptions",
    "compute_time_bounds",
]
