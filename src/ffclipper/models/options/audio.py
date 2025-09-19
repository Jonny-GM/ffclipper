"""Audio option models."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field

from ffclipper.models.annotations import EnableWhen

from .defaults import DEFAULT_AUDIO_KBPS
from .groups import AUDIO_GROUP


@Parameter(group=AUDIO_GROUP)
class AudioOptions(BaseModel):
    """Options for audio handling."""

    include: bool = Field(default=True, description="Include an audio track in the output.")
    copy: Annotated[
        bool,
        EnableWhen("audio.include", value=True),
    ] = Field(default=False, description="Copy the audio stream without re-encoding.")
    downmix_to_stereo: Annotated[
        bool,
        EnableWhen("audio.include", value=True),
        EnableWhen("audio.copy", value=False),
    ] = Field(default=True, description="Downmix audio to stereo when encoding.")
    kbps: Annotated[
        int | None,
        EnableWhen("audio.include", value=True),
        EnableWhen("audio.copy", value=False),
    ] = Field(
        None,
        gt=0,
        description=(f"Audio bitrate when transcoding, in kilobits per second. [default: {DEFAULT_AUDIO_KBPS}]"),
    )


__all__ = ["AudioOptions"]
