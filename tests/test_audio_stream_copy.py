"""Tests for audio stream copy and default handling."""

from pathlib import Path

import pytest

from ffclipper.models import ClipPlan, Options, RuntimeContext
from ffclipper.models.options import (
    DEFAULT_AUDIO_KBPS,
    AudioOptions,
)


def test_defaults_none_with_copy(source_file: Path) -> None:
    """Leave audio bitrate unset when stream copying."""
    opts = Options(source=source_file, audio=AudioOptions(copy=True, downmix_to_stereo=False))
    assert opts.audio.kbps is None
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    assert plan.opts.audio.kbps is None


def test_defaults_resolved_when_encoding(source_file: Path) -> None:
    """Resolve audio bitrate default when encoding."""
    opts = Options(source=source_file)
    assert opts.audio.kbps == DEFAULT_AUDIO_KBPS
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    assert plan.opts.audio.kbps == DEFAULT_AUDIO_KBPS


def test_defaults_none_without_audio(source_file: Path) -> None:
    """Clear audio bitrate when excluding audio."""
    opts = Options(source=source_file, audio=AudioOptions(include=False, downmix_to_stereo=False))
    assert opts.audio.kbps is None
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    assert plan.opts.audio.kbps is None


def test_invalid_audio_options(source_file: Path) -> None:
    """Reject invalid combinations of audio options."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            audio=AudioOptions(copy=True, kbps=192, downmix_to_stereo=False),
        )
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            audio=AudioOptions(include=False, kbps=192, downmix_to_stereo=False),
        )
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            audio=AudioOptions(include=False, copy=True, downmix_to_stereo=False),
        )
