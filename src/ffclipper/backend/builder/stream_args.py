"""Stream argument helpers."""

MAP_FLAG = "-map"  #: Flag to map a stream.


def spec(kind: str, index: int | None = 0, *, input_index: int = 0, optional: bool = False) -> str:
    """Return a formatted stream spec.

    Args:
        kind: Stream type identifier (e.g. "v", "a", "s").
        index: Stream index within the type or ``None`` to omit the index.
        input_index: Input file index.
        optional: Whether the stream should be optional.

    Returns:
        Formatted stream selector like ``0:v:0`` or ``0:s?``.

    """
    opt = "?" if optional else ""
    idx = "" if index is None else f":{index}"
    return f"{input_index}:{kind}{opt}{idx}"


def map_spec(
    kind: str,
    index: int | None = 0,
    *,
    input_index: int = 0,
    optional: bool = False,
) -> tuple[str, ...]:
    """Return ``-map`` argument for a stream spec."""
    return (MAP_FLAG, spec(kind, index, input_index=input_index, optional=optional))


def codec_flag(kind: str) -> tuple[str, ...]:
    """Return codec flag for a stream type."""
    return (f"-c:{kind}",)


def copy_stream(kind: str) -> tuple[str, ...]:
    """Return stream copy flags for a stream type."""
    return (*codec_flag(kind), "copy")


def bitrate_flag(kind: str) -> tuple[str, ...]:
    """Return bitrate flag for a stream type."""
    return (f"-b:{kind}",)


def disable_stream(kind: str) -> tuple[str, ...]:
    """Return flag to disable all streams of a type."""
    return (f"-{kind}n",)
