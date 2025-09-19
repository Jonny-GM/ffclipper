"""Shared pytest fixtures.

Provides a safe default during tests to prevent side effects like opening
system file explorers, and ensures Qt uses an offscreen backend.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

# Duration in seconds used by synthetic sample videos in tests.
VIDEO_DURATION_SEC: float = 4.0


@pytest.fixture(autouse=True)
def _no_open_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable opening directories during tests.

    Many code paths may call ``ffclipper.backend.executor.open_directory`` when
    ``open_dir`` defaults to True. Replace it with a no-op to avoid spawning
    OS windows during the test run. Individual tests can still override this
    with their own monkeypatch when they want to assert the call.
    """
    monkeypatch.setattr("ffclipper.backend.executor.open_directory", lambda _p: None)


@pytest.fixture(autouse=True)
def _qt_offscreen() -> None:
    """Force Qt to use the offscreen platform for GUI tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _tools_version_sanity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub tool version checks to avoid flaky native calls in tests."""
    monkeypatch.setattr("ffclipper.tools.get_ffmpeg_version", lambda: "test", raising=True)
    monkeypatch.setattr("ffclipper.tools.cli.check_ffmpeg_version", lambda _ctx: "test", raising=True)
    monkeypatch.setattr("ffclipper.tools.probe.check_version", lambda *args, **kwargs: None, raising=True)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    """Provide a small synthetic MP4 video for tests.

    Creates a 4-second 200x200 color clip using ffmpeg.
    Some encoders fail to encode much lower than 200x200.
    """
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg must be available in PATH for tests"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / "video.mp4"
    subprocess.run(  # noqa: S603
        [
            ffmpeg,
            "-v",
            "error",
            # Video source
            "-f",
            "lavfi",
            "-i",
            f"color=s=200x200:d={VIDEO_DURATION_SEC}",
            # Audio source (silent stereo)
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=48000:cl=stereo:d={VIDEO_DURATION_SEC}",
            # Shortest to match streams
            "-shortest",
            # Encode video and audio
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-y",
            str(out),
        ],
        check=True,
    )
    return out
