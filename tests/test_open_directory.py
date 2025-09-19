import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ffclipper.backend.executor import open_directory


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("win32", ["explorer", "/select,", "FILE"]),
        ("darwin", ["open", "-R", "FILE"]),
    ],
)
def test_open_directory_selects_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    platform: str,
    expected: list[str],
) -> None:
    file = (tmp_path / "out.mkv").resolve()
    file.touch()
    recorded: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], check: bool) -> None:
        recorded["cmd"] = cmd

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda _cmd: expected[0])
    open_directory(str(file))
    expected_cmd = expected.copy()
    expected_cmd[-1] = str(file)
    assert recorded["cmd"] == expected_cmd


def test_open_directory_linux_opens_parent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    file = (tmp_path / "out.mkv").resolve()
    file.touch()
    recorded: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], check: bool) -> None:
        recorded["cmd"] = cmd

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/xdg-open")
    open_directory(str(file))
    assert recorded["cmd"] == ["/usr/bin/xdg-open", str(file.parent)]
