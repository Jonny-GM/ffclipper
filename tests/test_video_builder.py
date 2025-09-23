"""Tests for video encoding helpers."""

from pathlib import Path

import pytest

from ffclipper.backend.builder import video
from ffclipper.models import ClipPlan, ColorTransfer, Encoder, Options, RuntimeContext
from ffclipper.models import plan as plan_module
from ffclipper.models.ffprobe import VideoColorInfo
from ffclipper.models.options import AudioOptions, VideoOptions
from ffclipper.tools import probe as probe_module
from tests.conftest import VIDEO_DURATION_SEC


def test_encode_applies_rate_multipliers(source_file: Path) -> None:
    """Peak rate and buffer size scale with defined multipliers."""
    opts = Options(source=source_file)
    plan = ClipPlan.from_options(opts, RuntimeContext())
    args = video.encode(plan, VIDEO_DURATION_SEC)
    bitrate_idx = args.index(video.BITRATE[0])
    kbps = int(args[bitrate_idx + 1][:-1])
    max_idx = args.index(video.MAXRATE[0])
    buf_idx = args.index(video.BUFSIZE[0])
    assert args[max_idx : max_idx + 2] == (
        *video.MAXRATE,
        f"{int(kbps * video.MAXRATE_MULTIPLIER)}k",
    )
    assert args[buf_idx : buf_idx + 2] == (
        *video.BUFSIZE,
        f"{int(kbps * video.BUFSIZE_MULTIPLIER)}k",
    )


def test_bitrate_reserves_target_size_mb_buffer(source_file: Path) -> None:
    """Bitrate calculation reserves space for container overhead."""
    opts = Options(
        source=source_file,
        audio=AudioOptions(include=False, downmix_to_stereo=False),
        target_size_mb=10,
    )
    plan = ClipPlan.from_options(opts, RuntimeContext())
    args = video.encode(plan, VIDEO_DURATION_SEC)
    bitrate_idx = args.index(video.BITRATE[0])
    kbps = int(args[bitrate_idx + 1][:-1])
    assert opts.target_size_mb is not None
    enc = plan.opts.video.encoder or Encoder.X264
    reserve = video.RESERVE_BY_ENCODER[enc]
    max_size = int(opts.target_size_mb * 1024 * 1024 * reserve)
    expected = max(100, int((max_size * 8) / (VIDEO_DURATION_SEC * 1000)))
    assert kbps == expected


@pytest.mark.parametrize("secs", [0, -1])
def test_bitrate_rejects_non_positive_duration(source_file: Path, secs: float) -> None:
    """Encode helper validates positive durations via bitrate calculation."""
    opts = Options(source=source_file)
    plan = ClipPlan.from_options(opts, RuntimeContext())
    with pytest.raises(ValueError):
        video.encode(plan, secs)


def test_nvenc_uses_fullres_multipass(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """NVENC encoding enables full-resolution multipass."""
    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.H264_NVENC})
    opts = Options(source=source_file, video=VideoOptions(encoder=Encoder.H264_NVENC))
    plan = ClipPlan.from_options(opts, RuntimeContext())
    args = video.encode(plan, VIDEO_DURATION_SEC)
    idx = args.index("-multipass")
    assert args[idx : idx + 2] == ("-multipass", "fullres")


def test_tonemap_added_for_hdr_to_h264(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """Tonemapping filter is inserted when converting HDR to H.264."""
    monkeypatch.setattr(
        probe_module,
        "get_video_color_info",
        lambda ctx, path: VideoColorInfo(transfer=ColorTransfer.PQ),
    )
    monkeypatch.setattr(video, "has_libplacebo", lambda _ctx: False)
    opts = Options(source=source_file)
    plan = ClipPlan.from_options(opts, RuntimeContext())
    assert plan.need_tonemap is True
    flt = video.filters(plan)
    assert any("tonemap" in f for f in flt)


def test_tonemap_uses_libplacebo_when_available(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """Libplacebo is used for tonemapping when available."""
    monkeypatch.setattr(
        probe_module,
        "get_video_color_info",
        lambda ctx, path: VideoColorInfo(transfer=ColorTransfer.PQ),
    )
    monkeypatch.setattr(video, "has_libplacebo", lambda _ctx: True)
    opts = Options(source=source_file)
    plan = ClipPlan.from_options(opts, RuntimeContext())
    flt = video.filters(plan)
    assert video.TONEMAP_LIBPLACEBO in flt


def test_tonemap_skipped_when_codec_supports_hdr(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """Tonemapping is skipped when the target codec supports HDR."""
    monkeypatch.setattr(
        probe_module,
        "get_video_color_info",
        lambda ctx, path: VideoColorInfo(transfer=ColorTransfer.PQ),
    )
    opts = Options(source=source_file, video=VideoOptions(encoder=Encoder.HEVC_NVENC))
    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.HEVC_NVENC})
    plan = ClipPlan.from_options(opts, RuntimeContext())
    assert plan.need_tonemap is False
    flt = video.filters(plan)
    assert all("tonemap" not in f for f in flt)
