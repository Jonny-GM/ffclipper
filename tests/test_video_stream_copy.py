"""Tests for video stream copy default resolution, encoder, and sizing."""

from pathlib import Path

import pytest

import ffclipper.models.plan as plan_module
from ffclipper.models import ClipPlan, Encoder, Options, Resolution, RuntimeContext
from ffclipper.models.options import DEFAULT_TARGET_SIZE_MB, VideoOptions


def test_defaults_none_with_copy(source_file: Path) -> None:
    """Leave encoding defaults unset when stream copying."""
    opts = Options(source=source_file, video=VideoOptions(copy=True))
    assert opts.video.encoder is None
    assert opts.video.resolution is None
    assert opts.target_size is None
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    assert plan.opts.video.encoder is None
    assert plan.opts.video.resolution is None
    assert plan.opts.target_size is None


def test_defaults_resolved_when_encoding(source_file: Path) -> None:
    """Resolve encoder, resolution, and target size defaults when encoding."""
    opts = Options(source=source_file)
    assert opts.video.encoder is Encoder.AUTO
    assert opts.video.resolution is Resolution.ORIGINAL
    assert opts.target_size == DEFAULT_TARGET_SIZE_MB
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.X264})
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    monkeypatch.undo()
    assert plan.opts.video.encoder is Encoder.X264
    assert plan.opts.video.resolution is Resolution.ORIGINAL
    assert plan.opts.target_size == DEFAULT_TARGET_SIZE_MB


def test_invalid_video_options(source_file: Path) -> None:
    """Reject encoding options when stream copying video."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True, resolution=Resolution.P720),
        )
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True, encoder=Encoder.H264_NVENC),
        )
