"""Time selection option models."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from cyclopts import Parameter
from pydantic import BaseModel, Field, field_validator, model_validator

from ffclipper.tools import parse_timespan_to_ms

from .groups import TIME_GROUP

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .options import Options as _OptionsType


@Parameter(group=TIME_GROUP)
class TimeOptions(BaseModel):
    """Options related to time selection."""

    TIME_DESC_TEMPLATE: ClassVar[str] = "{} for the clip. Examples: '90s', '1m20s', '00:01:30'."

    start: str | None = Field(None, description=TIME_DESC_TEMPLATE.format("Start timestamp"))
    end: str | None = Field(None, description=TIME_DESC_TEMPLATE.format("End timestamp"))
    duration: str | None = Field(None, description=TIME_DESC_TEMPLATE.format("Desired duration"))

    @field_validator("start", "end", "duration")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        """Ensure time strings are parseable."""
        if v is None:
            return v
        try:
            parse_timespan_to_ms(v)
        except ValueError as exc:  # pragma: no cover - re-raised for clarity
            raise ValueError(f"Invalid time format: {v}") from exc
        return v

    @model_validator(mode="after")
    def validate_time(self) -> TimeOptions:
        """Validate time options make logical sense."""
        if self.end is not None and self.duration is not None:
            raise ValueError("Cannot specify both 'end' and 'duration'")
        return self

    @cached_property
    def start_ms(self) -> int | None:
        """Start timestamp in milliseconds."""
        return parse_timespan_to_ms(self.start)

    @cached_property
    def end_ms(self) -> int | None:
        """End timestamp in milliseconds."""
        return parse_timespan_to_ms(self.end)

    @cached_property
    def duration_ms(self) -> int | None:
        """Duration in milliseconds."""
        return parse_timespan_to_ms(self.duration)


__all__ = ["TimeOptions"]


def compute_time_bounds(opts: _OptionsType, video_duration: float) -> tuple[int, int | None]:
    """Compute start and duration in milliseconds.

    Args:
        opts: Clipper options containing time fields.
        video_duration: Total video duration in seconds, as probed.

    Returns:
        A tuple of ``(start_ms, duration_ms_or_none)``. When no trim is set,
        returns the full duration.

    """
    start_ms = opts.time.start_ms or 0

    if opts.time.duration_ms is not None:
        duration = opts.time.duration_ms
    elif opts.time.end_ms is not None:
        duration = opts.time.end_ms - start_ms
    elif opts.time.start_ms is not None:
        duration = int((video_duration - (start_ms / 1000.0)) * 1000)
    else:
        duration = int(video_duration * 1000)

    if duration <= 0:
        raise ValueError("Computed duration must be greater than 0")

    return start_ms, duration


__all__ += ["compute_time_bounds"]
