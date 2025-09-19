"""Runtime option models."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field, field_validator

from ffclipper.models.annotations import EnableWhen
from ffclipper.models.verbosity import Verbosity

from .groups import RUNTIME_GROUP


@Parameter(group=RUNTIME_GROUP)
class RuntimeOptions(BaseModel):
    """Runtime behavior options."""

    verbosity: Verbosity = Field(
        default=Verbosity.QUIET,
        description=("Increase logging verbosity. Commands: show FFmpeg commands; Output: also show FFmpeg output."),
    )
    dry_run: bool = Field(default=False, description="Print FFmpeg commands without executing them.")
    open_dir: Annotated[
        bool,
        EnableWhen("runtime.dry_run", value=False),
    ] = Field(default=True, description="Open the output directory when done.")

    @field_validator("verbosity", mode="before")
    @classmethod
    def _parse_verbosity(cls, v: object) -> Verbosity:
        """Accept numeric values or case-insensitive enum names.

        Allows CLI usage like ``--runtime.verbosity commands`` in addition to
        ``--runtime.verbosity 1``.
        """
        if isinstance(v, Verbosity):
            return v
        if isinstance(v, int):
            return Verbosity(v)
        if isinstance(v, str):
            token = v.strip()
            try:
                return Verbosity[token.upper()]
            except KeyError:
                try:
                    return Verbosity(int(token))
                except (ValueError, KeyError):
                    pass
        raise ValueError("verbosity must be one of quiet, commands, output, or 0/1/2")


__all__ = ["RuntimeOptions"]
