"""Tests for command builder."""

from pathlib import Path

import pytest

from ffclipper.backend.builder import command_builder, trim, video
from ffclipper.backend.builder.command_args import INPUT_FLAG
from ffclipper.backend.builder.command_builder import (
    GLOBAL_FLAGS,
    _trim_args,
    build_command,
)
from ffclipper.models import ClipPlan, ColorTransfer, Options, RuntimeContext
from ffclipper.models.ffprobe import VideoColorInfo
from ffclipper.models.options import AudioOptions, TimeOptions, VideoOptions
from ffclipper.models.plan import CLIP_SUFFIX
from ffclipper.tools import probe as probe_module


def test_command_builder_basic(source_file: Path) -> None:
    """Build FFmpeg command with default options."""
    opts = Options(source=source_file)
    plan = ClipPlan.from_options(opts, RuntimeContext())
    args, output = build_command(plan)
    prefix_len = len(GLOBAL_FLAGS)
    assert args[:prefix_len] == GLOBAL_FLAGS
    assert args[prefix_len : prefix_len + 2] == (*INPUT_FLAG, str(source_file))
    # Extension follows the plan's selected container
    assert output.endswith(f"{source_file.stem}{CLIP_SUFFIX}.{plan.opts.container.value}")
    assert args[-1] == output


def test_command_builder_with_trim(source_file: Path) -> None:
    """Include trim arguments when start and end are set."""
    opts = Options(source=source_file, time=TimeOptions(start="00:00:01", end="00:00:03"))
    plan = ClipPlan.from_options(opts, RuntimeContext())
    args, _ = build_command(plan)
    prefix_len = len(GLOBAL_FLAGS)
    assert args[prefix_len : prefix_len + 4] == (
        "-ss",
        "00:00:01.000",
        "-t",
        "00:00:02.000",
    )


def test_copy_trim_returns_pre_and_post(source_file: Path) -> None:
    """Fast copy trim splits arguments around the input."""
    opts = Options(
        source=source_file,
        time=TimeOptions(start="00:00:01", end="00:00:03"),
        video=VideoOptions(copy=True),
        audio=AudioOptions(copy=True, downmix_to_stereo=False),
    )
    plan = ClipPlan.from_options(opts, RuntimeContext())
    pre, post = _trim_args(plan)
    assert pre == ("-noaccurate_seek", "-ss", "00:00:01.000")
    assert post == ("-t", "00:00:02.000")
    args, _ = build_command(plan)
    prefix_len = len(GLOBAL_FLAGS)
    assert args[prefix_len : prefix_len + len(pre)] == pre
    idx = prefix_len + len(pre)
    assert args[idx : idx + 2] == (*INPUT_FLAG, str(source_file))
    assert args[idx + 2 : idx + 2 + len(post)] == post


def test_keyframe_trim_when_fast_copy_disabled(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """Keyframe copy trim when fast stream copy is disabled."""
    monkeypatch.setattr(command_builder, "FAST_STREAM_COPY", False)
    monkeypatch.setattr(
        probe_module,
        "snap_window_copy_bounds",
        lambda ctx, path, start, end: (1.0, 3.0),
    )
    opts = Options(
        source=source_file,
        time=TimeOptions(start="00:00:01", end="00:00:03"),
        video=VideoOptions(copy=True),
        audio=AudioOptions(copy=True, downmix_to_stereo=False),
    )
    plan = ClipPlan.from_options(opts, RuntimeContext())
    pre, post = _trim_args(plan)
    assert post == ()
    assert pre == (
        *trim.SEEK2ANY,
        *trim.START,
        "00:00:01.000",
        *trim.END,
        "00:00:03.000",
        *trim.COPYTS,
    )


def test_command_builder_inits_vulkan_for_libplacebo_tonemap(
    monkeypatch: pytest.MonkeyPatch, source_file: Path
) -> None:
    """Initialize Vulkan when tonemapping with libplacebo."""
    monkeypatch.setattr(
        probe_module,
        "get_video_color_info",
        lambda ctx, path: VideoColorInfo(transfer=ColorTransfer.PQ),
    )
    monkeypatch.setattr(video, "has_libplacebo", lambda _ctx: True)
    opts = Options(source=source_file)
    plan = ClipPlan.from_options(opts, RuntimeContext())
    args, _ = build_command(plan)
    flag = video.TONEMAP_HW_DEVICE[0]
    assert flag in args
    idx = args.index(flag)
    assert args[idx : idx + len(video.TONEMAP_HW_DEVICE)] == video.TONEMAP_HW_DEVICE
