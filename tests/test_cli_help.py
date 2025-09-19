"""Tests for command-line interface help output."""

import shutil
import subprocess


def test_help_hides_internal_options() -> None:
    """`ffclipper --help` does not expose internal parameters like status_callback."""
    ffclipper = shutil.which("ffclipper")
    assert ffclipper
    result = subprocess.run(  # noqa: S603
        [ffclipper, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert "status-callback" not in result.stdout
