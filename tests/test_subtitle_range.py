import shutil
import subprocess
from pathlib import Path

import pytest

from ffclipper.backend.builder import subs
from ffclipper.backend.executor import run_conversion
from ffclipper.models import Options, RuntimeContext, SubtitleBurnMethod
from ffclipper.models.options import AudioOptions, RuntimeOptions, SubtitlesOptions, TimeOptions
from ffclipper.models.plan import ClipPlan
from ffclipper.models.types import Container


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


def test_run_conversion_skips_burn_when_no_subtitles(sample_video_with_subs: Path, tmp_path: Path) -> None:
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0),
        time=TimeOptions(start="3", duration="1"),
        runtime=RuntimeOptions(dry_run=False),
    )
    commands, _ = run_conversion(opts)
    assert "subtitles" not in " ".join(commands[-1])


def test_run_conversion_burns_when_subtitles_present(sample_video_with_subs: Path, tmp_path: Path) -> None:
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0),
        time=TimeOptions(start="0", duration="2"),
        runtime=RuntimeOptions(dry_run=False),
    )
    commands, _ = run_conversion(opts)
    assert any("subtitles" in a for a in commands[-1])


def test_prepare_burn_includes_itsoffset(
    sample_video_with_subs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prepare_burn inserts ``-itsoffset`` for subtitle delay."""
    captured: dict[str, tuple[str, ...]] = {}

    original = subs.prepare_burn

    def fake_prepare(plan: ClipPlan) -> tuple[str, ...]:
        args = original(plan)
        captured["args"] = args
        return args

    monkeypatch.setattr(subs, "prepare_burn", fake_prepare)
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(
            burn=0,
            burn_method=SubtitleBurnMethod.EXTRACT,
            delay=1000,
        ),
        time=TimeOptions(start="0", duration="2"),
        runtime=RuntimeOptions(dry_run=True),
    )
    run_conversion(opts)
    args = captured["args"]
    assert "-itsoffset" in args
    idx = args.index("-itsoffset")
    assert float(args[idx + 1]) == pytest.approx(1.0)


def test_prepare_burn_seeks_before_input(sample_video_with_subs: Path, tmp_path: Path) -> None:
    """Start and duration options precede the input file."""
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.EXTRACT),
        time=TimeOptions(start="1", duration="1"),
        runtime=RuntimeOptions(dry_run=True),
    )
    plan = ClipPlan.from_options(opts, RuntimeContext(dry_run=True))
    args = subs.prepare_burn(plan)
    assert "-ss" in args
    assert "-i" in args
    ss_indices = [i for i, a in enumerate(args) if a == "-ss"]
    i_idx = args.index("-i")
    assert ss_indices[0] < i_idx
    assert any(idx > i_idx for idx in ss_indices[1:])
    assert "-t" in args
    assert args.index("-t") > i_idx


def test_subtitle_delay_shifts_burned_timing(sample_video_with_subs: Path, tmp_path: Path) -> None:
    """Subtitle delay shifts cue timing before trim."""
    out = tmp_path / "out.mkv"
    opts = Options(
        source=sample_video_with_subs,
        output=out,
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, delay=1000),
        audio=AudioOptions(include=False, downmix_to_stereo=False),
        time=TimeOptions(start="1", duration="2"),
        runtime=RuntimeOptions(dry_run=False),
    )
    run_conversion(opts)
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    frame1 = tmp_path / "frame1.png"
    subprocess.run(  # noqa: S603
        [ffmpeg, "-v", "0", "-ss", "0.5", "-i", str(out), "-frames:v", "1", str(frame1)],
        check=True,
    )
    frame2 = tmp_path / "frame2.png"
    subprocess.run(  # noqa: S603
        [ffmpeg, "-v", "0", "-ss", "1.5", "-i", str(out), "-frames:v", "1", str(frame2)],
        check=True,
    )
    assert frame1.read_bytes() != frame2.read_bytes()
