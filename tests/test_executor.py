"""Tests for FFmpeg execution helpers."""

import os
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from ffclipper.backend import executor
from ffclipper.backend.builder.command_builder import build_command
from ffclipper.models import ClipPlan, Encoder, Options, RuntimeContext, SubtitleBurnMethod
from ffclipper.models.options import (
    DEFAULT_CONTAINER,
    AudioOptions,
    RuntimeOptions,
    SubtitlesOptions,
    TimeOptions,
    VideoOptions,
)
from ffclipper.models.types import Container
from ffclipper.models.verbosity import Verbosity
from ffclipper.tools import probe


def test_run_conversion_dry_run(source_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Return command and output without running ffmpeg on dry run."""
    called = False

    def fake_run_ffmpeg(*_args, **_kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(executor, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(executor.uuid, "uuid4", lambda: uuid.UUID(int=0))
    opts = Options(
        source=source_file,
        runtime=RuntimeOptions(dry_run=True),
        video=VideoOptions(encoder=Encoder.X264),
    )
    runtime = RuntimeContext(verbosity=opts.runtime.verbosity, dry_run=opts.runtime.dry_run)
    plan = ClipPlan.from_options(opts, runtime)
    expected_args, expected_output = build_command(plan, stats_id="00000000000000000000000000000000")
    commands, result = executor.run_conversion(opts)
    assert not called
    assert len(commands) == 2
    assert commands[1] == expected_args
    assert result.success
    assert result.output == expected_output


def test_two_pass_stats_cleanup(source_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove encoder pass stats files after conversion."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(executor.uuid, "uuid4", lambda: uuid.UUID(int=0))

    def fake_run_ffmpeg(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(executor, "run_ffmpeg", fake_run_ffmpeg)
    stats_base = "00000000000000000000000000000000"
    (tmp_path / f"{stats_base}.x264-0.log").write_text("stats")
    (tmp_path / f"{stats_base}.x264-0.log.mbtree").write_text("stats")
    executor.run_conversion(Options(source=source_file, video=VideoOptions(encoder=Encoder.X264)))
    assert not (tmp_path / f"{stats_base}.x264-0.log").exists()
    assert not (tmp_path / f"{stats_base}.x264-0.log.mbtree").exists()


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (1, (False, True)),
        (2, (True, True)),
    ],
)
def test_run_conversion_verbosity_levels(
    source_file: Path, monkeypatch: pytest.MonkeyPatch, level: int, expected: tuple[bool, bool]
) -> None:
    """Pass correct flags to ffmpeg based on verbosity."""
    calls: list[tuple[bool, bool]] = []

    def fake_run_ffmpeg(
        args: tuple[str, ...],
        *,
        verbose: bool,
        status_callback: Callable[[str], None] | None = None,
        list_cmd: bool = False,
    ) -> str:
        calls.append((verbose, list_cmd))
        return ""

    monkeypatch.setattr(executor, "run_ffmpeg", fake_run_ffmpeg)
    opts = Options(
        source=source_file,
        runtime=RuntimeOptions(verbosity=Verbosity(level)),
        video=VideoOptions(encoder=Encoder.X264),
    )
    executor.run_conversion(opts)
    assert len(calls) == 2
    assert all(c == expected for c in calls)


def test_run_conversion_full(source_file: Path) -> None:
    """Run ffmpeg and produce a trimmed output clip."""
    opts = Options(source=source_file, time=TimeOptions(start="00:00:01", end="00:00:03"))
    commands, result = executor.run_conversion(opts)
    assert result.success
    assert result.output is not None
    out_path = Path(result.output)
    assert out_path.is_file()
    duration = probe.get_video_duration_sec(RuntimeContext(), result.output)
    assert duration is not None
    assert 1.9 <= duration <= 2.1


def test_run_conversion_stream_copy(source_file: Path) -> None:
    """Stream copy audio and video and produce trimmed clip."""
    probe.clear_cache()
    opts = Options(
        source=source_file,
        time=TimeOptions(start="00:00:01", end="00:00:03"),
        video=VideoOptions(copy=True),
        audio=AudioOptions(copy=True, downmix_to_stereo=False),
    )
    runtime = RuntimeContext()
    plan = ClipPlan.from_options(opts, runtime)
    expected_args, expected_output = build_command(plan)
    assert "-c:v" in expected_args
    assert expected_args[expected_args.index("-c:v") + 1] == "copy"
    assert "-c:a" in expected_args
    assert expected_args[expected_args.index("-c:a") + 1] == "copy"
    commands, result = executor.run_conversion(opts)
    assert commands == (expected_args,)
    assert result.success
    assert result.output is not None
    assert result.output == expected_output
    out_path = Path(result.output)
    assert out_path.is_file()
    duration = probe.get_video_duration_sec(RuntimeContext(), result.output)
    assert duration is not None
    assert duration < 4.1


def test_ffclipper_end_to_end(source_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Run the high-level ffclipper flow to encode a clip."""
    probe.clear_cache()
    opts = Options(source=source_file, time=TimeOptions(start="00:00:01", end="00:00:02"))

    output = source_file.with_name(f"{source_file.stem}_clip.{DEFAULT_CONTAINER.value}")
    output.unlink(missing_ok=True)
    code = executor.ffclipper(opts)
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out == str(output.absolute())
    assert output.is_file()
    duration = probe.get_video_duration_sec(RuntimeContext(), str(output))
    assert duration is not None
    assert 0.9 <= duration <= 1.1


def test_run_conversion_custom_output(source_file: Path, tmp_path: Path) -> None:
    """Place the output file at a custom path."""
    custom = tmp_path / "nested" / "custom_output.mkv"
    opts = Options(
        source=source_file,
        time=TimeOptions(start="00:00:01", end="00:00:02"),
        output=custom,
        container=Container.MKV,
    )
    commands, result = executor.run_conversion(opts)
    assert result.success
    assert result.output == str(custom)
    assert commands[-1][-1] == str(custom)
    assert custom.parent.is_dir()
    assert custom.is_file()


def test_output_parent_must_be_directory(source_file: Path, tmp_path: Path) -> None:
    """Fail conversion when output parent path is a file."""
    parent = tmp_path / "blocking"
    parent.write_text("not a directory")
    output = parent / "clip.mkv"
    opts = Options(
        source=source_file,
        output=output,
        container=Container.MKV,
        runtime=RuntimeOptions(dry_run=True),
    )
    commands, result = executor.run_conversion(opts)
    assert commands == ()
    assert not result.success
    assert result.error.startswith(executor.CONVERSION_FAILED)
    assert str(parent) in result.error


@pytest.fixture
def sample_video_with_subs(tmp_path: Path) -> Path:
    srt = tmp_path / "subs.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nhello\n")
    video = tmp_path / "video.mkv"
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    subprocess.run(  # noqa: S603
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=200x200:d=4",
            "-i",
            str(srt),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:s",
            "srt",
            "-map",
            "0",
            "-map",
            "1",
            "-y",
            str(video),
        ],
        check=True,
    )
    return video


def test_dry_run_lists_extract_and_final(sample_video_with_subs: Path, tmp_path: Path) -> None:
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.EXTRACT),
        runtime=RuntimeOptions(dry_run=True),
        video=VideoOptions(encoder=Encoder.X264),
    )
    commands, _ = executor.run_conversion(opts)
    assert len(commands) == 3
    assert commands[0][-1].endswith(".srt")
    assert commands[1][-1] == os.devnull
    assert commands[2][-1] == str(tmp_path / "out.mkv")
