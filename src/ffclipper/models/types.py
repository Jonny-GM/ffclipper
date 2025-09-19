"""Codec and container type definitions."""

from dataclasses import dataclass
from enum import Enum


class VideoCodec(str, Enum):
    """Video codec options."""

    H264 = "h264"
    HEVC = "hevc"
    AV1 = "av1"
    VP9 = "vp9"
    MPEG4 = "mpeg4"

    @property
    def supports_hdr(self) -> bool:
        """Whether this codec can carry HDR content."""
        return self in HDR_CAPABLE_CODECS


HDR_CAPABLE_CODECS: set[VideoCodec] = {VideoCodec.HEVC, VideoCodec.AV1, VideoCodec.VP9}


class AudioCodec(str, Enum):
    """Audio codec options."""

    AAC = "aac"
    MP3 = "mp3"
    AC3 = "ac3"
    EAC3 = "eac3"
    DTS = "dts"
    FLAC = "flac"
    OPUS = "opus"
    VORBIS = "vorbis"


class SubtitleCodec(str, Enum):
    """Subtitle codec options."""

    SRT = "srt"
    ASS = "ass"
    SSA = "ssa"
    PGS = "pgs"
    VOBSUB = "vobsub"
    MOV_TEXT = "mov_text"


class SubtitleBurnMethod(str, Enum):
    """Strategies for burning subtitles into the video."""

    AUTO = "auto"
    EXTRACT = "extract"
    INLINE = "inline"


class ColorTransfer(str, Enum):
    """Color transfer characteristics."""

    PQ = "smpte2084"
    HLG = "arib-std-b67"

    @property
    def is_hdr(self) -> bool:
        """Whether this transfer represents HDR content."""
        return self in {ColorTransfer.PQ, ColorTransfer.HLG}


class Encoder(str, Enum):
    """Supported video encoders."""

    AUTO = "auto"
    X264 = "x264"
    X265 = "x265"
    H264_NVENC = "h264-nvenc"
    HEVC_NVENC = "hevc-nvenc"
    SVT_AV1 = "svt-av1"

    @property
    def ffmpeg_name(self) -> str:
        """Return the FFmpeg encoder name for this enum."""
        return {
            Encoder.X264: "libx264",
            Encoder.X265: "libx265",
            Encoder.H264_NVENC: "h264_nvenc",
            Encoder.HEVC_NVENC: "hevc_nvenc",
            Encoder.SVT_AV1: "libsvtav1",
            Encoder.AUTO: "auto",
        }[self]

    @property
    def codec(self) -> VideoCodec:
        """Video codec produced by this encoder."""
        if self is Encoder.AUTO:
            raise ValueError("AUTO encoder has no codec")
        return {
            Encoder.X264: VideoCodec.H264,
            Encoder.X265: VideoCodec.HEVC,
            Encoder.H264_NVENC: VideoCodec.H264,
            Encoder.HEVC_NVENC: VideoCodec.HEVC,
            Encoder.SVT_AV1: VideoCodec.AV1,
        }[self]


class Resolution(str, Enum):
    """Output video resolutions."""

    ORIGINAL = "original"
    P2160 = "2160p"
    P1440 = "1440p"
    P1080 = "1080p"
    P720 = "720p"
    P480 = "480p"

    @property
    def height(self) -> int | None:
        """Vertical resolution in pixels or ``None`` for the original height."""
        return None if self == Resolution.ORIGINAL else int(self.value[:-1])


class Container(str, Enum):
    """Supported output container formats."""

    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"

    @property
    def compatibility(self) -> "ContainerCompatibility":
        """Capabilities supported by this container."""
        return _CONTAINER_COMPATIBILITY[self]

    @property
    def extension(self) -> str:
        """Canonical filename extension for this container, including dot."""
        return f".{self.value}"


@dataclass(frozen=True)
class ContainerCompatibility:
    """Capabilities supported by an output container."""

    video_codecs: set[VideoCodec]
    audio_codecs: set[AudioCodec]
    subtitle_codecs: set[SubtitleCodec]


_CONTAINER_COMPATIBILITY: dict[Container, ContainerCompatibility] = {
    Container.MKV: ContainerCompatibility(
        video_codecs={
            VideoCodec.H264,
            VideoCodec.HEVC,
            VideoCodec.AV1,
            VideoCodec.VP9,
            VideoCodec.MPEG4,
        },
        audio_codecs={
            AudioCodec.AAC,
            AudioCodec.MP3,
            AudioCodec.AC3,
            AudioCodec.EAC3,
            AudioCodec.DTS,
            AudioCodec.FLAC,
            AudioCodec.OPUS,
            AudioCodec.VORBIS,
        },
        subtitle_codecs={
            SubtitleCodec.SRT,
            SubtitleCodec.ASS,
            SubtitleCodec.SSA,
            SubtitleCodec.PGS,
            SubtitleCodec.VOBSUB,
        },
    ),
    Container.MP4: ContainerCompatibility(
        video_codecs={VideoCodec.H264, VideoCodec.HEVC, VideoCodec.AV1},
        audio_codecs={AudioCodec.AAC, AudioCodec.MP3, AudioCodec.AC3},
        subtitle_codecs={SubtitleCodec.MOV_TEXT},
    ),
    Container.WEBM: ContainerCompatibility(
        video_codecs={VideoCodec.VP9, VideoCodec.AV1},
        audio_codecs={AudioCodec.OPUS, AudioCodec.VORBIS},
        subtitle_codecs=set(),
    ),
}
