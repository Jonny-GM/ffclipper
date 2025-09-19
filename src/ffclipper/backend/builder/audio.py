"""Audio stream argument helpers."""

from ffclipper.models import Container, Options

from .stream_args import bitrate_flag, codec_flag, copy_stream, disable_stream, map_spec

MAP: tuple[str, ...] = map_spec("a")  #: Select the first audio stream from the input.
CODEC: tuple[str, ...] = codec_flag("a")  #: Audio codec flag used to specify encoder or copy mode.
COPY: tuple[str, ...] = copy_stream("a")  #: Pass audio stream through without re-encoding.
TRANSCODE_AAC: tuple[str, ...] = (*CODEC, "aac")  #: Encode audio to AAC.
TRANSCODE_OPUS: tuple[str, ...] = (*CODEC, "libopus")  #: Encode audio to Opus.
BITRATE: tuple[str, ...] = bitrate_flag("a")  #: Target audio bitrate.
DOWNMIX_STEREO: tuple[str, ...] = ("-ac", "2")  #: Downmix audio to stereo.
DISABLE: tuple[str, ...] = disable_stream("a")  #: Drop all audio streams.


def encode(opts: Options) -> tuple[str, ...]:
    """Return args to encode audio for the selected container."""
    codec = TRANSCODE_OPUS if opts.container == Container.WEBM else TRANSCODE_AAC
    args = MAP + codec
    if opts.audio.downmix_to_stereo:
        args = args + DOWNMIX_STEREO
    return args + BITRATE + (f"{opts.audio.kbps}k",)


def copy() -> tuple[str, ...]:
    """Return args to stream copy the first audio track."""
    return MAP + COPY
