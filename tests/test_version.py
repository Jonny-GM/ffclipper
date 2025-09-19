"""Tests for FFmpeg/ffprobe version checks."""

from pathlib import Path

import pytest

from ffclipper.models import ClipPlan, Options, RuntimeContext
from ffclipper.tools import cli, probe


def test_options_requires_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Options validation fails when FFmpeg is missing."""
    src = tmp_path / "a.mp4"
    src.touch()

    def _raise(_ctx: RuntimeContext) -> str:
        raise RuntimeError("missing ffmpeg")

    monkeypatch.setattr(cli, "check_ffmpeg_version", _raise)
    with pytest.raises(ValueError):
        ClipPlan.from_options(
            Options(source=src),
            RuntimeContext(),
        )


def test_options_requires_ffprobe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Options validation fails when ffprobe is missing."""
    src = tmp_path / "b.mp4"
    src.touch()

    def _raise(_ctx: RuntimeContext) -> str:
        raise RuntimeError("missing ffprobe")

    monkeypatch.setattr(probe, "check_version", _raise)
    with pytest.raises(ValueError):
        ClipPlan.from_options(
            Options(source=src),
            RuntimeContext(),
        )
