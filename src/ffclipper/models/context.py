"""Runtime context shared across ffclipper components."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Self

from diskcache import Cache

from ffclipper.models.verbosity import Verbosity

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

_CACHE_DIR = Path(os.getenv("FFCLIPPER_CACHE", tempfile.gettempdir())) / "ffclipper-cache"


def _default_cache() -> Cache:
    """Return a cache for ffclipper operations."""
    return Cache(str(_CACHE_DIR))


@dataclass(slots=True)
class RuntimeContext:
    """Runtime flags and cache for probing and encoding."""

    verbosity: Verbosity = Verbosity.QUIET
    dry_run: bool = False
    status_callback: Callable[[str], None] | None = None
    cache: Cache = field(default_factory=_default_cache)
    burn_subtitle_path: Path | None = None

    def close(self) -> None:
        """Close any open resources."""
        self.cache.close()

    def __enter__(self) -> Self:
        """Return ``self`` when entering a context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close resources when exiting a context."""
        self.close()

    def __del__(self) -> None:  # pragma: no cover - cleanup
        """Ensure cache is closed on garbage collection."""
        with suppress(Exception):
            self.cache.close()


__all__ = ["RuntimeContext"]
