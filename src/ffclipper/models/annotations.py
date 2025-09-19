"""Pydantic field annotations used to drive GUI behavior."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnableWhen:
    """GUI hint to enable a field based on another option's value."""

    key: str
    value: object = True
    not_none: bool = False
