"""Dataclasses for ffprobe outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ColorTransfer


@dataclass(frozen=True)
class SubtitleTrack:
    """Information about a subtitle stream."""

    index: int
    language: str
    title: str
    codec: str
    display: str


@dataclass(frozen=True)
class VideoInfo:
    """Video stream metadata."""

    codec: str | None = None


@dataclass(frozen=True)
class VideoColorInfo:
    """Color characteristics for a video stream."""

    primaries: str | None = None
    transfer: ColorTransfer | None = None
    space: str | None = None


@dataclass(frozen=True)
class AudioInfo:
    """Audio stream metadata."""

    codec: str | None = None
    bitrate: int | None = None
