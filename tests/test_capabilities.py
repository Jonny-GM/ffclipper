import subprocess
from pathlib import Path

import pytest
from diskcache import Cache

import ffclipper.models.plan as plan_module
from ffclipper.models import ClipPlan, Options, RuntimeContext
from ffclipper.models.options import VideoOptions
from ffclipper.models.types import Encoder, VideoCodec
from ffclipper.tools import capabilities


def test_available_encoders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Discover encoders by attempting a tiny encode."""
    attempted: list[str] = []

    def fake_run(args: list[str], **_: dict) -> str:
        enc = args[args.index("-c:v") + 1]
        attempted.append(enc)
        if enc == Encoder.X264.ffmpeg_name:
            return ""
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(capabilities, "run_ffmpeg", fake_run)
    ctx = RuntimeContext(cache=Cache(str(tmp_path)))
    res = capabilities.available_encoders(ctx)
    expected_args = [e.ffmpeg_name for e in Encoder if e is not Encoder.AUTO]
    assert attempted == expected_args
    assert res == {Encoder.X264}
    # Cached result
    res2 = capabilities.available_encoders(ctx)
    assert res2 == {Encoder.X264}
    assert attempted == expected_args


def test_has_libplacebo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Detect libplacebo filter by attempting a tiny filter graph."""
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: dict) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(capabilities, "run_ffmpeg", fake_run)
    ctx = RuntimeContext(cache=Cache(str(tmp_path)))
    assert capabilities.has_libplacebo(ctx) is True
    expected = [
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
    assert calls == [expected]
    calls.clear()
    assert capabilities.has_libplacebo(ctx) is True
    assert calls == []


def test_plan_requires_available_encoder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Plan creation fails when the selected encoder is missing."""
    src = tmp_path / "a.mp4"
    src.touch()

    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.X264})
    with pytest.raises(ValueError):
        ClipPlan.from_options(
            Options(source=src, video=VideoOptions(encoder=Encoder.HEVC_NVENC)),
            RuntimeContext(),
        )


def test_plan_auto_selects_best_encoder(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """Automatically choose best encoder for requested codec."""
    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.H264_NVENC})
    plan = ClipPlan.from_options(
        Options(source=source_file, video=VideoOptions(codec=VideoCodec.H264)),
        RuntimeContext(),
    )
    assert plan.opts.video.encoder is Encoder.H264_NVENC

    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.X264})
    plan2 = ClipPlan.from_options(
        Options(source=source_file, video=VideoOptions(codec=VideoCodec.H264)),
        RuntimeContext(),
    )
    assert plan2.opts.video.encoder is Encoder.X264

    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: {Encoder.X265})
    plan3 = ClipPlan.from_options(
        Options(source=source_file, video=VideoOptions(codec=VideoCodec.HEVC)),
        RuntimeContext(),
    )
    assert plan3.opts.video.encoder is Encoder.X265

    monkeypatch.setattr(plan_module, "available_encoders", lambda _ctx: set())
    with pytest.raises(ValueError):
        ClipPlan.from_options(
            Options(source=source_file, video=VideoOptions(codec=VideoCodec.H264)),
            RuntimeContext(),
        )
