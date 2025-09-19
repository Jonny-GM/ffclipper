"""Subtitle option models."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field, model_validator

from ffclipper.models.annotations import EnableWhen
from ffclipper.models.types import SubtitleBurnMethod

from .defaults import DEFAULT_SUBTITLE_DELAY
from .groups import SUBTITLES_GROUP


@Parameter(group=SUBTITLES_GROUP)
class SubtitlesOptions(BaseModel):
    """Options related to subtitles."""

    include: bool = Field(
        default=False,
        description=(
            "Include subtitle tracks in the output when the container supports them. "
            "This is independent of subtitle burn-in."
        ),
    )
    burn: int | None = Field(None, ge=0, description="Subtitle stream index to burn into the video.")
    burn_method: Annotated[
        SubtitleBurnMethod | None,
        EnableWhen("subtitles.burn", not_none=True),
    ] = Field(
        None,
        description=(
            "Strategy for burning subtitles: 'auto', 'extract', or 'inline'. "
            f"[default: {SubtitleBurnMethod.AUTO.value}]"
        ),
    )
    delay: Annotated[
        int | None,
        EnableWhen("subtitles.burn", not_none=True),
    ] = Field(
        None,
        le=10000,
        ge=-10000,
        description=(f"Delay to apply when burning subtitles, in milliseconds. [default: {DEFAULT_SUBTITLE_DELAY}]"),
    )

    @model_validator(mode="after")
    def apply_subtitle_defaults(self) -> SubtitlesOptions:
        """Resolve subtitle defaults based on burn settings."""
        if self.burn is None:
            if self.burn_method is not None:
                raise ValueError("burn_method requires burn")
            if self.delay is not None:
                raise ValueError("delay requires burn")
        else:
            if self.burn_method is None:
                self.burn_method = SubtitleBurnMethod.AUTO
            if self.delay is None:
                self.delay = DEFAULT_SUBTITLE_DELAY
        return self


__all__ = ["SubtitlesOptions"]
