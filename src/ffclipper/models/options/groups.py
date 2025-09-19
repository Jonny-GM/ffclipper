"""Shared Cyclopts groups for option models."""

from __future__ import annotations

from cyclopts import Group

SOURCE_GROUP = Group.create_ordered("Source")
OUTPUT_GROUP = Group.create_ordered("Output")
TOTAL_BITRATE_GROUP = Group.create_ordered("Total Bitrate")
TIME_GROUP = Group.create_ordered("Time")
VIDEO_GROUP = Group.create_ordered("Video")
AUDIO_GROUP = Group.create_ordered("Audio")
SUBTITLES_GROUP = Group.create_ordered("Subtitles")
RUNTIME_GROUP = Group.create_ordered("Runtime")

__all__ = [
    "AUDIO_GROUP",
    "OUTPUT_GROUP",
    "RUNTIME_GROUP",
    "SOURCE_GROUP",
    "SUBTITLES_GROUP",
    "TIME_GROUP",
    "TOTAL_BITRATE_GROUP",
    "VIDEO_GROUP",
]
