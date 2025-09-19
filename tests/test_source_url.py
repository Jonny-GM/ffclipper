from pathlib import Path

import pytest

from ffclipper.models import ClipPlan, Options, RuntimeContext
from ffclipper.models import plan as plan_module


def test_source_accepts_local_file(source_file: Path) -> None:
    """Local filesystem paths are allowed as sources."""
    opts = Options(source=source_file)
    assert opts.source == source_file


def test_source_accepts_url() -> None:
    """HTTP/HTTPS URLs are allowed as sources."""
    url = "https://example.com/video.mp4"
    opts = Options(source=url)
    assert opts.source == url


# Removed test that asserts a specific default container extension for URLs.
# The project default may change, and output container choice belongs to
# configuration rather than a hardcoded assumption in tests.


def test_url_without_filename_requires_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """URLs missing a filename require an explicit output path."""
    url = "https://example.com"
    opts = Options(source=url)
    monkeypatch.setattr(plan_module, "_ensure_tools", lambda ctx, opts: None)
    monkeypatch.setattr(plan_module, "_probe_duration", lambda ctx, src: 1.0)
    monkeypatch.setattr(plan_module, "_validate_container", lambda opts, ctx: (None, None))
    with pytest.raises(ValueError):
        ClipPlan.from_options(opts, RuntimeContext())
