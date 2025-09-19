"""Option models and validation logic (moved out of package __init__)."""

from __future__ import annotations

from enum import Enum, IntEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from cyclopts import Parameter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ffclipper.models.annotations import EnableWhen
from ffclipper.models.types import AudioCodec, Container, Encoder, SubtitleBurnMethod
from ffclipper.models.verbosity import Verbosity

from .audio import AudioOptions
from .defaults import (
    DEFAULT_AUDIO_KBPS,
    DEFAULT_CONTAINER,
    DEFAULT_ENCODER,
    DEFAULT_RESOLUTION,
    DEFAULT_SUBTITLE_DELAY,
    DEFAULT_TARGET_SIZE_MB,
)
from .groups import OUTPUT_GROUP, SOURCE_GROUP, TOTAL_BITRATE_GROUP
from .runtime import RuntimeOptions
from .subtitles import SubtitlesOptions
from .time import TimeOptions
from .video import VideoOptions


@Parameter(name="*")
class Options(BaseModel):
    """Options for the video conversion script."""

    source: Annotated[
        Path | str,
        Parameter(group=SOURCE_GROUP),
    ] = Field(
        description="Path or URL to the source video.",
    )
    output: Annotated[
        Path | None,
        Parameter(group=OUTPUT_GROUP),
    ] = Field(
        default=None,
        description=("Path for the output file. Defaults to appending '_clip' to the source name."),
    )
    container: Annotated[
        Container,
        Parameter(group=OUTPUT_GROUP),
    ] = Field(
        DEFAULT_CONTAINER,
        description=f"Container format for the output file. [default: {DEFAULT_CONTAINER.value}]",
    )
    target_size: Annotated[
        int | None,
        Parameter(group=TOTAL_BITRATE_GROUP),
        EnableWhen("video.copy", value=False),
    ] = Field(
        None,
        gt=0,
        description=(f"Approximate target file size in megabytes when encoding. [default: {DEFAULT_TARGET_SIZE_MB}]"),
    )
    time: TimeOptions = Field(default_factory=TimeOptions)
    audio: AudioOptions = Field(default_factory=AudioOptions)
    video: VideoOptions = Field(default_factory=VideoOptions)
    subtitles: SubtitlesOptions = Field(default_factory=SubtitlesOptions)
    runtime: RuntimeOptions = Field(default_factory=RuntimeOptions)

    model_config = ConfigDict(extra="forbid")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: Path | str) -> Path | str:
        """Ensure local sources exist; allow remote URLs."""
        if isinstance(v, Path):
            path = v.expanduser().absolute()
            if not path.is_file():
                raise ValueError(f"Input path is not a file: {path}")
            return path
        parsed = urlparse(v)
        if parsed.scheme in {"http", "https"}:
            return v
        path = Path(v).expanduser().absolute()
        if not path.is_file():
            raise ValueError(f"Input path is not a file: {path}")
        return path

    @field_validator("output")
    @classmethod
    def validate_output(cls, v: Path | None) -> Path | None:
        """Normalize output path; creation happens later when executing a plan."""
        if v is None:
            return None
        return Path(v).expanduser().absolute()

    @model_validator(mode="before")
    @classmethod
    def infer_container_from_output(cls, data: dict) -> dict:
        """Infer container from an explicit output file extension.

        - If the user provided an ``--output`` with a recognized extension and
          did not explicitly pass ``--container``, set the container based on
          the extension.
        - If both were provided and conflict, raise a clear error.
        - If the output has no or an unrecognized extension, leave the
          container unchanged and allow other validators to handle defaults.
        """
        output = data.get("output")
        if output is None:
            return data
        out_str = str(output)
        suffix = Path(out_str).suffix.lower() if out_str else ""
        if not suffix:
            return data
        ext = suffix.lstrip(".")
        try:
            container = Container(ext)
        except ValueError:
            return data
        # If container provided and conflicts, raise
        provided = data.get("container")
        if provided is None:
            data["container"] = container
            return data
        if isinstance(provided, Container) and provided != container:
            raise ValueError(f"Output extension '{suffix}' conflicts with explicit container '{provided.value}'.")
        return data

    @model_validator(mode="after")
    def validate_codec_against_container(self) -> Options:
        """Validate selected video codec is compatible with the container.

        Treat a missing codec as the default codec implied by
        ``DEFAULT_ENCODER`` for validation. Skip checks when stream copying.
        """
        if self.video.copy:
            return self
        if self.container is None:
            raise ValueError("container not resolved")
        compat = self.container.compatibility
        codec = self.video.codec or DEFAULT_ENCODER.codec
        if codec not in compat.video_codecs:
            raise ValueError(f"Video codec '{codec}' not supported in {self.container} container")
        return self

    @model_validator(mode="after")
    def validate_audio_codec(self) -> Options:
        """Validate audio settings against container capabilities."""
        if self.audio.include and not self.audio.copy:
            if self.container is None:
                raise ValueError("container not resolved")
            compat = self.container.compatibility
            audio_codec = AudioCodec.OPUS if self.container == Container.WEBM else AudioCodec.AAC
            if audio_codec not in compat.audio_codecs:
                raise ValueError(f"{audio_codec.value.upper()} audio not supported in {self.container} container")
        return self

    @model_validator(mode="after")
    def validate_stream_copy_constraints(self) -> Options:
        """Ensure options are compatible with stream copy operations."""
        if self.video.copy:
            # Video-specific constraints
            if self.subtitles.burn is not None:
                raise ValueError("Cannot burn subtitles when stream copying video")
            if self.video.resolution is not None:
                raise ValueError("resolution requires video encoding")
            if self.video.codec is not None:
                raise ValueError("codec requires video encoding")
            if self.video.encoder not in {None, Encoder.AUTO}:
                raise ValueError("encoder requires video encoding")
            # Global constraints influenced by video encoding
            if self.target_size is not None:
                raise ValueError("target_size requires video encoding")
            # Normalize: clear encoder when copying
            self.video.encoder = None
        return self

    @model_validator(mode="after")
    def validate_audio_constraints(self) -> Options:
        """Validate audio include/copy/downmix/bitrate combinations."""
        if self.audio.copy:
            if self.audio.downmix_to_stereo:
                raise ValueError("downmix_to_stereo requires audio encoding")
            if self.audio.kbps is not None:
                raise ValueError("audio bitrate requires audio encoding")
        if not self.audio.include:
            if self.audio.kbps is not None:
                raise ValueError("audio bitrate requires audio inclusion")
            if self.audio.copy:
                raise ValueError("audio stream copy requires audio inclusion")
        return self

    @model_validator(mode="after")
    def apply_target_size_default(self) -> Options:
        """Resolve target size defaults based on stream copy."""
        if self.video.copy:
            if self.target_size is not None:
                raise ValueError("target_size requires video encoding")
        elif self.target_size is None:
            self.target_size = DEFAULT_TARGET_SIZE_MB
        return self

    @model_validator(mode="after")
    def apply_encoding_defaults(self) -> Options:
        """Apply default values for encoding-related fields when appropriate."""
        if not self.video.copy:
            if self.video.codec is None:
                if self.video.encoder not in {None, Encoder.AUTO}:
                    self.video.codec = self.video.encoder.codec
                else:
                    self.video.codec = DEFAULT_ENCODER.codec
            if self.video.resolution is None:
                self.video.resolution = DEFAULT_RESOLUTION
            if self.audio.include and not self.audio.copy and self.audio.kbps is None:
                self.audio.kbps = DEFAULT_AUDIO_KBPS
        return self

    @model_validator(mode="after")
    def validate_output_matches_container(self) -> Options:
        """Ensure explicit output suffix matches the selected container.

        If ``--output`` includes a file extension, it must match the chosen
        ``--container`` exactly. This avoids mismatched muxer flags and codec
        defaults.
        """
        if self.output is None or self.container is None:
            return self
        suffix = self.output.suffix.lower()
        if not suffix:
            return self
        if suffix != self.container.extension:
            raise ValueError(f"Output extension '{suffix}' does not match selected container '{self.container.value}'.")
        return self

    @model_validator(mode="after")
    def validate_codec_encoder_match(self) -> Options:
        """Ensure explicitly selected codec matches the chosen encoder.

        Only enforced when not stream copying and both values are provided.
        """
        # Only validate mismatch when the codec was explicitly provided by the user.
        explicit_codec = "codec" in self.video.model_fields_set
        if (
            not self.video.copy
            and explicit_codec
            and self.video.encoder not in {None, Encoder.AUTO}
            and self.video.encoder.codec != self.video.codec
        ):
            raise ValueError("Selected encoder does not match selected codec")
        return self

    def to_cli_args(self, *, suppress_output: bool = False, baseline: Options | None = None) -> list[str]:
        """Return CLI argument list representing this option set."""
        baseline_opts = baseline or self.defaults_for_gui()
        args: list[str] = ["--source", str(self.source)]
        flat_actual = self._flatten_dict(self.model_dump())
        flat_defaults = self._flatten_dict(baseline_opts.model_dump())
        for key, value in self._diff_pairs(flat_defaults, flat_actual):
            if suppress_output and key == "output":
                continue
            cli_key = self._to_cli_key(key)
            if isinstance(value, bool):
                args.append(f"--{cli_key}" if value else f"--{self._negate(cli_key)}")
                continue
            if value is None:
                continue
            args.extend([f"--{cli_key}", self._to_cli_value(value)])
        return args

    @classmethod
    def _flatten_dict(cls, data: dict[str, object], prefix: str | None = None) -> list[tuple[str, object]]:
        items: list[tuple[str, object]] = []
        for name, value in data.items():
            fq = f"{prefix}.{name}" if prefix else name
            if isinstance(value, dict):
                items.extend(cls._flatten_dict(value, fq))
            else:
                items.append((fq, value))
        return items

    @staticmethod
    def _diff_pairs(defaults: list[tuple[str, object]], actual: list[tuple[str, object]]) -> list[tuple[str, object]]:
        default_map = dict(defaults)
        result: list[tuple[str, object]] = []
        for key, value in actual:
            if key == "source":
                continue
            if default_map.get(key) != value:
                result.append((key, value))
        return result

    @staticmethod
    def _to_cli_key(dotted: str) -> str:
        return ".".join(part.replace("_", "-") for part in dotted.split("."))

    @staticmethod
    def _negate(cli_key: str) -> str:
        parts = cli_key.split(".")
        parts[-1] = f"no-{parts[-1]}"
        return ".".join(parts)

    @staticmethod
    def _to_cli_value(value: object) -> str:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, IntEnum):
            return value.name.lower()
        if isinstance(value, Enum):
            return str(value.value)
        return str(value)

    @classmethod
    def defaults_for_gui(cls) -> Options:
        """Construct ``Options`` with sensible GUI defaults without validation.

        This avoids validating ``source`` while providing initial values for
        dropdowns and fields that otherwise default to ``None``.
        """
        opts = cls.model_construct()
        # Output/container
        opts.container = DEFAULT_CONTAINER
        # Video (when not copying)
        opts.video.codec = DEFAULT_ENCODER.codec
        opts.video.encoder = Encoder.AUTO
        opts.video.resolution = DEFAULT_RESOLUTION
        # Audio (when included and not copying)
        if opts.audio.include and not opts.audio.copy:
            opts.audio.kbps = DEFAULT_AUDIO_KBPS
        # Target size (when encoding video)
        if not opts.video.copy:
            opts.target_size = DEFAULT_TARGET_SIZE_MB
        # Subtitles UI helpers
        if opts.subtitles.burn is None:
            opts.subtitles.burn_method = SubtitleBurnMethod.AUTO
            opts.subtitles.delay = DEFAULT_SUBTITLE_DELAY
        return opts

    @classmethod
    def supports_subtitle_copying(cls, container: Container) -> bool:
        """Check if container supports subtitle streams in any form."""
        compat = container.compatibility
        return bool(compat.subtitle_codecs)

    def should_burn_subtitles(self) -> bool:
        """Check if we should burn subtitles based on current settings."""
        return self.subtitles.burn is not None and not self.video.copy

    def should_copy_subtitles(self) -> bool:
        """Check if we should copy subtitle streams (for execution)."""
        return self.container is not None and self.subtitles.include and self.supports_subtitle_copying(self.container)


__all__ = [
    "DEFAULT_AUDIO_KBPS",
    "DEFAULT_CONTAINER",
    "DEFAULT_ENCODER",
    "DEFAULT_RESOLUTION",
    "DEFAULT_SUBTITLE_DELAY",
    "DEFAULT_TARGET_SIZE_MB",
    "AudioOptions",
    "Options",
    "RuntimeOptions",
    "SubtitlesOptions",
    "TimeOptions",
    "Verbosity",
    "VideoOptions",
]
