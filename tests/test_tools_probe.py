"""Tests for ffprobe helper caching."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import time
from typing import TYPE_CHECKING, Never

from diskcache import Cache

from ffclipper.tools import probe

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

probe_module = importlib.import_module("ffclipper.tools.probe")


def test_run_caches_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache ``ffprobe`` failures to avoid repeated executions."""
    calls = {"count": 0}

    def fake_run_ffprobe(
        cmd: list[str],
        *,
        verbose: bool,
        status_callback: Callable[[str], None] | None = None,
        list_cmd: bool = False,
    ) -> Never:
        calls["count"] += 1
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(probe_module, "run_ffprobe", fake_run_ffprobe)

    cache = Cache(str(tmp_path))
    ctx = probe.RuntimeContext(cache=cache)

    cmd = ["-version"]
    assert probe.run(ctx, cmd) is None
    assert calls["count"] == 1
    assert probe.run(ctx, cmd) is None
    assert calls["count"] == 1


def test_run_includes_file_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalidate cache when probed file metadata changes."""
    calls = {"count": 0}

    def fake_run_ffprobe(
        cmd: list[str],
        *,
        verbose: bool,
        status_callback: Callable[[str], None] | None = None,
        list_cmd: bool = False,
    ) -> str:
        calls["count"] += 1
        return "data"

    monkeypatch.setattr(probe_module, "run_ffprobe", fake_run_ffprobe)

    cache = Cache(str(tmp_path / "cache"))
    ctx = probe.RuntimeContext(cache=cache)

    media = tmp_path / "a.mp4"
    media.write_text("a")
    cmd = [str(media)]

    assert probe.run(ctx, cmd) == "data"
    assert calls["count"] == 1
    assert probe.run(ctx, cmd) == "data"
    assert calls["count"] == 1

    media.write_text("bigger")
    assert probe.run(ctx, cmd) == "data"
    assert calls["count"] == 2

    time.sleep(0.01)
    os.utime(media, None)
    assert probe.run(ctx, cmd) == "data"
    assert calls["count"] == 3


def test_get_audio_codec(tmp_path: Path, source_file: Path) -> None:
    """Return audio codec information for a clip."""
    local_src = tmp_path / source_file.name
    shutil.copy(source_file, local_src)
    ctx = probe.RuntimeContext()
    info = probe.get_audio_codec(ctx, str(local_src))
    assert info is not None
    assert info.codec == "aac"


def test_get_audio_bitrate(tmp_path: Path, source_file: Path) -> None:
    """Return audio bitrate information for a clip."""
    local_src = tmp_path / source_file.name
    shutil.copy(source_file, local_src)
    ctx = probe.RuntimeContext()
    info = probe.get_audio_bitrate(ctx, str(local_src))
    assert info is not None
    assert info.bitrate is not None
    assert info.bitrate > 0
