"""Tests for option helpers."""

from pathlib import Path

import pytest

import ffclipper.models.types as mtypes
from ffclipper.models import Options
from ffclipper.models.options import (
    AudioOptions,
    SubtitlesOptions,
    TimeOptions,
    VideoOptions,
    compute_time_bounds,
)
from ffclipper.models.types import Container, Encoder, Resolution, VideoCodec

from .conftest import VIDEO_DURATION_SEC

START_TS = "00:00:01"
END_TS = "00:00:03"
START_MS = 1_000
DURATION_MS = 2_000


def test_compute_trim_bounds_with_end(source_file: Path) -> None:
    """Compute trim bounds when end timestamp is provided."""
    opts = Options(source=source_file, time=TimeOptions(start=START_TS, end=END_TS))
    start_ms, duration_ms = compute_time_bounds(opts, VIDEO_DURATION_SEC)
    assert start_ms == START_MS
    assert duration_ms == DURATION_MS


def test_compute_trim_bounds_without_end(source_file: Path) -> None:
    """Compute duration using video length when only start is provided."""
    opts = Options(source=source_file, time=TimeOptions(start=START_TS))
    start_ms, duration_ms = compute_time_bounds(opts, VIDEO_DURATION_SEC)
    expected_duration = int(VIDEO_DURATION_SEC * 1000) - START_MS
    assert start_ms == START_MS
    assert duration_ms == expected_duration


@pytest.mark.parametrize(
    "trim",
    [
        TimeOptions(duration="0"),
        TimeOptions(start=START_TS, end=START_TS),
        TimeOptions(start=END_TS, end=START_TS),
        TimeOptions(start="00:00:05"),
    ],
)
def test_compute_trim_bounds_invalid_durations(source_file: Path, trim: TimeOptions) -> None:
    """Reject zero or negative durations."""
    opts = Options(source=source_file, time=trim)
    with pytest.raises(ValueError):
        compute_time_bounds(opts, VIDEO_DURATION_SEC)


def test_time_options_rejects_invalid_format() -> None:
    """Reject invalid time strings."""
    with pytest.raises(ValueError):
        TimeOptions(start="notatime")


def test_validate_stream_copy_constraints_resolution(source_file: Path) -> None:
    """Reject resolution change when stream copying video."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True, resolution=Resolution.P720),
        )


def test_validate_stream_copy_constraints_encoder(source_file: Path) -> None:
    """Reject encoder selection when stream copying video."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True, encoder=Encoder.H264_NVENC),
        )


def test_validate_stream_copy_constraints_codec(source_file: Path) -> None:
    """Reject codec selection when stream copying video."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True, codec=VideoCodec.HEVC),
        )


def test_validate_stream_copy_constraints_target_size_mb(source_file: Path) -> None:
    """Reject target size control when stream copying video."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True),
            target_size_mb=20,
        )


def test_validate_audio_codec_requires_encoding(source_file: Path) -> None:
    """Reject downmix when audio stream copy is enabled."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            audio=AudioOptions(copy=True, downmix_to_stereo=True),
        )


def test_validate_stream_copy_constraints_burn_subtitles(source_file: Path) -> None:
    """Reject subtitle burn-in when stream copying video."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(copy=True),
            subtitles=SubtitlesOptions(burn=0),
        )


def test_validate_video_encoder_incompatible(source_file: Path) -> None:
    """Reject incompatible encoder/container combination."""
    with pytest.raises(ValueError):
        Options(source=source_file, container=Container.WEBM)


def test_validate_codec_encoder_mismatch(source_file: Path) -> None:
    """Reject mismatched codec and encoder selection."""
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            video=VideoOptions(codec=VideoCodec.HEVC, encoder=Encoder.X264),
        )


def test_validate_codec_encoder_match(source_file: Path) -> None:
    """Accept matching codec and encoder selection."""
    opts = Options(
        source=source_file,
        video=VideoOptions(codec=VideoCodec.HEVC, encoder=Encoder.HEVC_NVENC),
    )
    assert opts.video.codec is VideoCodec.HEVC
    assert opts.video.encoder is Encoder.HEVC_NVENC


def test_validate_audio_codec_incompatible(monkeypatch: pytest.MonkeyPatch, source_file: Path) -> None:
    """Reject unsupported audio codec for container."""
    current = mtypes._CONTAINER_COMPATIBILITY[mtypes.Container.WEBM]  # noqa: SLF001
    compat = mtypes.ContainerCompatibility(
        video_codecs=current.video_codecs,
        audio_codecs=set(),
        subtitle_codecs=set(),
    )
    monkeypatch.setitem(
        mtypes._CONTAINER_COMPATIBILITY,  # noqa: SLF001
        mtypes.Container.WEBM,
        compat,
    )
    with pytest.raises(ValueError):
        Options(
            source=source_file,
            container=Container.WEBM,
            video=VideoOptions(encoder=Encoder.SVT_AV1),
        )
