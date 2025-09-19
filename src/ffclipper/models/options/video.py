"""Video option models."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field

from ffclipper.models.annotations import EnableWhen
from ffclipper.models.types import Encoder, Resolution, VideoCodec

from .defaults import DEFAULT_ENCODER, DEFAULT_RESOLUTION
from .groups import VIDEO_GROUP


def _resolution_choice_transform(name: str) -> str:
    """Map Enum member names to their values for help choices."""
    try:
        return Resolution[name].value
    except KeyError:
        return name.lower()


@Parameter(group=VIDEO_GROUP)
class VideoOptions(BaseModel):
    """Options for video encoding."""

    copy: bool = Field(default=False, description="Copy the video stream without re-encoding.")
    codec: Annotated[
        VideoCodec | None,
        EnableWhen("video.copy", value=False),
    ] = Field(
        None,
        description=(f"Target video codec when auto-selecting an encoder. [default: {DEFAULT_ENCODER.codec.value}]"),
    )
    encoder: Annotated[
        Encoder | None,
        EnableWhen("video.copy", value=False),
    ] = Field(Encoder.AUTO, description="Video encoder to use when encoding.")
    resolution: Annotated[
        Resolution | None,
        EnableWhen("video.copy", value=False),
        Parameter(name_transform=_resolution_choice_transform),  # type: ignore[call-arg]
    ] = Field(
        None,
        description=(
            f'Output video resolution or "original" to keep the source. [default: {DEFAULT_RESOLUTION.value}]'
        ),
    )


__all__ = ["VideoOptions"]
