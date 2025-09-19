import shutil
import subprocess
from pathlib import Path

import pytest

from ffclipper.backend.builder import subs
from ffclipper.backend.executor import run_conversion
from ffclipper.models import ClipPlan, Options, RuntimeContext, SubtitleBurnMethod
from ffclipper.models import plan as plan_module
from ffclipper.models.options import AudioOptions, RuntimeOptions, SubtitlesOptions, TimeOptions
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


def test_defaults_none_without_burn(sample_video_with_subs: Path) -> None:
    opts = Options(source=sample_video_with_subs)
    assert opts.subtitles.burn_method is None
    assert opts.subtitles.delay is None
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    assert plan.subtitle_burn_method is None
    assert plan.subtitle_delay is None


def test_defaults_resolved_with_burn(sample_video_with_subs: Path) -> None:
    opts = Options(source=sample_video_with_subs, subtitles=SubtitlesOptions(burn=0))
    assert opts.subtitles.burn_method is SubtitleBurnMethod.AUTO
    assert opts.subtitles.delay == 0
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    assert plan.subtitle_burn_method is SubtitleBurnMethod.INLINE
    assert plan.subtitle_delay == 0


def test_invalid_subtitle_options(sample_video_with_subs: Path) -> None:
    with pytest.raises(ValueError):
        Options(
            source=sample_video_with_subs,
            subtitles=SubtitlesOptions(burn_method=SubtitleBurnMethod.AUTO),
        )
    with pytest.raises(ValueError):
        Options(source=sample_video_with_subs, subtitles=SubtitlesOptions(delay=500))


def test_inline_method_skips_extraction(
    sample_video_with_subs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fake_prepare(plan: ClipPlan) -> tuple[str, ...]:
        nonlocal called
        called = True
        dummy = tmp_path / "dummy.srt"
        dummy.touch()
        plan.ctx.burn_subtitle_path = dummy
        return ()

    monkeypatch.setattr(subs, "prepare_burn", fake_prepare)
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.INLINE),
        time=TimeOptions(start="0", duration="2"),
        runtime=RuntimeOptions(dry_run=True),
    )
    run_conversion(opts)
    assert not called


def test_extract_method_invokes_prepare(
    sample_video_with_subs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fake_prepare(plan: ClipPlan) -> tuple[str, ...]:
        nonlocal called
        called = True
        dummy = tmp_path / "dummy.srt"
        dummy.touch()
        plan.ctx.burn_subtitle_path = dummy
        return ()

    monkeypatch.setattr(subs, "prepare_burn", fake_prepare)
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.EXTRACT),
        time=TimeOptions(start="0", duration="2"),
        runtime=RuntimeOptions(dry_run=True),
    )
    run_conversion(opts)
    assert called


def test_auto_method_uses_ratio(sample_video_with_subs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_module, "AUTO_EXTRACT_RATIO_THRESHOLD", 0.5)
    short_opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "short.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.AUTO),
        audio=AudioOptions(include=False, downmix_to_stereo=False),
        time=TimeOptions(start="0", duration="1"),
    )
    with RuntimeContext() as ctx:
        short_plan = ClipPlan.from_options(short_opts, ctx)
    assert short_plan.subtitle_burn_method is SubtitleBurnMethod.EXTRACT

    long_opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "long.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.AUTO),
        audio=AudioOptions(include=False, downmix_to_stereo=False),
        time=TimeOptions(start="0", duration="3"),
    )
    with RuntimeContext() as ctx:
        long_plan = ClipPlan.from_options(long_opts, ctx)
    assert long_plan.subtitle_burn_method is SubtitleBurnMethod.INLINE


def test_burn_filter_requires_prepare(sample_video_with_subs: Path, tmp_path: Path) -> None:
    opts = Options(
        source=sample_video_with_subs,
        output=tmp_path / "out.mkv",
        container=Container.MKV,
        subtitles=SubtitlesOptions(burn=0, burn_method=SubtitleBurnMethod.EXTRACT),
    )
    with RuntimeContext() as ctx:
        plan = ClipPlan.from_options(opts, ctx)
    with pytest.raises(FileNotFoundError):
        subs.burn_filter(plan)
