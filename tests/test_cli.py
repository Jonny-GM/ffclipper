"""Tests for CLI entry point."""

import shutil
from pathlib import Path

import pytest

from ffclipper.cli import main
from ffclipper.models.options import DEFAULT_CONTAINER
from ffclipper.tools import probe


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Display help message without error."""
    code = main(["--help"])
    out = capsys.readouterr().out
    assert code in (0, None)
    assert "ffclipper" in out
    assert "--source" in out


def test_cli_conversion(tmp_path: Path, source_file: Path) -> None:
    """Run the CLI to trim a clip end-to-end."""
    local_src = tmp_path / source_file.name
    shutil.copy(source_file, local_src)
    code = main(
        [
            "--source",
            str(local_src),
            "--time.start",
            "00:00:01",
            "--time.end",
            "00:00:02",
        ]
    )
    assert code == 0
    output = local_src.with_name(f"{local_src.stem}_clip.{DEFAULT_CONTAINER.value}")
    assert output.is_file()
    duration = probe.get_video_duration_sec(probe.RuntimeContext(), str(output))
    assert duration is not None
    assert 0.9 <= duration <= 1.1


def test_cli_custom_output(tmp_path: Path, source_file: Path) -> None:
    """Run the CLI specifying a custom output file."""
    local_src = tmp_path / source_file.name
    shutil.copy(source_file, local_src)
    custom = tmp_path / "nested" / "myclip.mkv"
    code = main(
        [
            "--source",
            str(local_src),
            "--time.start",
            "00:00:01",
            "--time.end",
            "00:00:02",
            "--container",
            "mkv",
            "--output",
            str(custom),
        ]
    )
    assert code == 0
    assert custom.parent.is_dir()
    assert custom.is_file()


def test_cli_open_dir(tmp_path: Path, source_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the CLI with --open-dir and open containing folder."""
    local_src = tmp_path / source_file.name
    shutil.copy(source_file, local_src)
    recorded: dict[str, str] = {}

    def fake_open(path: str) -> None:
        recorded["path"] = path

    monkeypatch.setattr("ffclipper.backend.executor.open_directory", fake_open)
    code = main(
        [
            "--source",
            str(local_src),
            "--time.start",
            "00:00:01",
            "--time.end",
            "00:00:02",
            "--runtime.open-dir",
        ]
    )
    assert code == 0
    expected = local_src.with_name(f"{local_src.stem}_clip.{DEFAULT_CONTAINER.value}")
    assert recorded["path"] == str(expected)
