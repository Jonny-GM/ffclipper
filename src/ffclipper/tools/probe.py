"""ffprobe helpers and probing utilities."""

from __future__ import annotations

import bisect
import json
import logging
import math
import subprocess
from typing import TYPE_CHECKING

from ffclipper.models.context import RuntimeContext
from ffclipper.models.ffprobe import AudioInfo, SubtitleTrack, VideoColorInfo, VideoInfo
from ffclipper.models.types import ColorTransfer
from ffclipper.models.verbosity import Verbosity

from .cli import cache_key, get_ffprobe_version, join_command, run_ffprobe
from .helpers import emit_status, format_action_label

if TYPE_CHECKING:
    from collections.abc import Callable

_QUIET = ["-v", "quiet"]
_CSV_OUTPUT = ["-of", "csv=p=0"]
_JSON_OUTPUT = ["-of", "json"]
_SHOW_ENTRIES = ["-show_entries"]
_SELECT_STREAMS = ["-select_streams"]
_READ_INTERVALS = ["-read_intervals"]
_SKIP_FRAME = ["-skip_frame"]
_SKIP_NOKEY = [*_SKIP_FRAME, "nokey"]
_SHOW_FRAMES = ["-show_frames"]
_SHOW_PACKETS = ["-show_packets"]
FFPROBE_SUBTITLE_STREAM = "s"
FFPROBE_SUBTITLE_ENTRIES = "stream=index,codec_name:stream_tags=language,title"
FRAME_BEST_EFFORT = "frame=best_effort_timestamp_time"
FRAME_PKT_PTS = "frame=pkt_pts_time"
PACKET_PTS_FLAGS = "packet=pts_time,flags"
DEFAULT_PAD_S = 6.0
PAD_EDGE_MULTIPLIER = 2
PAD_GROWTH_FACTOR = 2
MAX_PAD_ATTEMPTS = 3
END_BOUNDARY_FALLBACK_DELTA = 0.1
MAX_DEBUG_KFS = 5

EXPECTED_KF_PARTS = 2
FLAGGED_APPROACH_INDEX = 2


_VERSION_KEY = "__ffprobe_version__"

logger = logging.getLogger(__name__)

_CACHE_FAILURE_ENTRY: tuple[bool, str | None] = (False, None)
_CACHE_ENTRY_LENGTH = 2


def _decode_cache_entry(value: object) -> tuple[bool, str | None]:
    """Normalize ffprobe cache entries."""
    if isinstance(value, tuple) and len(value) == _CACHE_ENTRY_LENGTH and isinstance(value[0], bool):
        ok, payload = value
        if payload is None or isinstance(payload, str):
            return ok, payload
        return ok, str(payload)
    if value is None or isinstance(value, str):
        return True, value
    return True, str(value)


def _log_cmd(ctx: RuntimeContext, cmd: list[str], *, cached: bool = False) -> None:
    """Log an ffprobe command banner with consistent labeling and routing."""
    action = format_action_label(dry_run=ctx.dry_run, cached=cached)
    emit_status(
        f"{action}: {join_command('ffprobe', cmd)}",
        status_callback=ctx.status_callback,
    )


def clear_cache(ctx: RuntimeContext | None = None) -> None:
    """Clear shared cache."""
    (ctx or RuntimeContext()).cache.clear()


def check_version(ctx: RuntimeContext) -> str:
    """Return the ``ffprobe`` version string."""
    version_obj = ctx.cache.get(_VERSION_KEY)
    if isinstance(version_obj, str):
        return version_obj
    try:
        version = get_ffprobe_version()
    except FileNotFoundError as e:  # pragma: no cover - system-dependent
        raise RuntimeError("ffprobe not found") from e
    except subprocess.CalledProcessError as e:  # pragma: no cover - unlikely
        raise RuntimeError(f"ffprobe failed: {e}") from e
    ctx.cache[_VERSION_KEY] = version
    return version


def run(ctx: RuntimeContext, cmd: list[str]) -> str | None:
    """Run ``ffprobe`` with ``cmd`` and return stripped output or ``None``."""
    key = cache_key(["ffprobe", *cmd])
    if key in ctx.cache:
        cached = ctx.cache[key]
        if ctx.verbosity >= Verbosity.COMMANDS:
            _log_cmd(ctx, cmd, cached=True)
        ok, payload = _decode_cache_entry(cached)
        return payload if ok else None
    if ctx.verbosity >= Verbosity.COMMANDS:
        _log_cmd(ctx, cmd)
    try:
        out = run_ffprobe(
            cmd,
            verbose=ctx.verbosity >= Verbosity.OUTPUT,
            status_callback=ctx.status_callback,
            list_cmd=False,
        ).strip()
    except subprocess.CalledProcessError as exc:
        command = join_command("ffprobe", cmd)
        logger.warning("ffprobe command failed (%s): %s", exc.returncode, command, exc_info=exc)
        if ctx.verbosity >= Verbosity.COMMANDS:
            emit_status(
                f"ffprobe failed ({exc.returncode}): {command}",
                status_callback=ctx.status_callback,
            )
        ctx.cache[key] = _CACHE_FAILURE_ENTRY
        return None
    result = out or None
    ctx.cache[key] = (True, result)
    return result


def query[T](
    ctx: RuntimeContext,
    path: str,
    query: str,
    stream: str = "",
    *,
    convert: Callable[[str], T] | None = None,
) -> T | str | None:
    """Execute a generic ``ffprobe`` query."""
    cmd = _QUIET + ([*_SELECT_STREAMS, stream] if stream else []) + _SHOW_ENTRIES + [query] + _CSV_OUTPUT + [path]
    out = run(ctx, cmd)
    if not out:
        return None
    if convert is None:
        return out
    try:
        return convert(out)
    except (ValueError, TypeError):
        return None


def get_video_duration_sec(ctx: RuntimeContext, path: str) -> float | None:
    """Get video duration in seconds."""
    dur = query(ctx, path, "format=duration", convert=float)
    return dur if isinstance(dur, (int, float)) else None


def get_video_codec(ctx: RuntimeContext, path: str) -> VideoInfo | None:
    """Get video codec information."""
    codec = query(ctx, path, "stream=codec_name", "v:0")
    return VideoInfo(codec=codec) if codec else None


def get_video_color_info(ctx: RuntimeContext, path: str) -> VideoColorInfo | None:
    """Get color metadata for the first video stream."""
    primaries = query(ctx, path, "stream=color_primaries", "v:0")
    transfer_raw = query(ctx, path, "stream=color_transfer", "v:0")
    space = query(ctx, path, "stream=color_space", "v:0")
    transfer: ColorTransfer | None = None
    if transfer_raw:
        try:
            transfer = ColorTransfer(transfer_raw)
        except ValueError:
            transfer = None
    if not any([primaries, transfer, space]):
        return None
    return VideoColorInfo(primaries=primaries, transfer=transfer, space=space)


def get_audio_bitrate(ctx: RuntimeContext, path: str) -> AudioInfo | None:
    """Get audio bitrate information."""
    br = query(ctx, path, "stream=bit_rate", "a:0", convert=lambda s: int(int(s) / 1000))
    return AudioInfo(bitrate=br) if isinstance(br, int) else None


def get_audio_codec(ctx: RuntimeContext, path: str) -> AudioInfo | None:
    """Get audio codec information."""
    codec = query(ctx, path, "stream=codec_name", "a:0")
    return AudioInfo(codec=codec) if codec else None


def get_subtitle_tracks(ctx: RuntimeContext, video_path: str) -> list[SubtitleTrack]:
    """Get subtitle track information from a video file."""
    cmd = (
        _QUIET
        + _SELECT_STREAMS
        + [FFPROBE_SUBTITLE_STREAM]
        + _SHOW_ENTRIES
        + [FFPROBE_SUBTITLE_ENTRIES]
        + _JSON_OUTPUT
        + [video_path]
    )
    out = run(ctx, cmd)
    if not out:
        return []
    try:
        data = json.loads(out)

        def build_track(i: int, stream: dict) -> SubtitleTrack:
            tags = stream.get("tags", {})
            language = tags.get("language", "und")
            title = tags.get("title", "")
            codec = stream.get("codec_name", "")
            parts = [f"Track {i}: {language}"]
            if title:
                parts.append(f"- {title}")
            if codec:
                parts.append(f"({codec})")
            return SubtitleTrack(
                index=i,
                display=" ".join(parts),
                language=language,
                title=title,
                codec=codec,
            )

        streams = data.get("streams", [])
        return [build_track(i, s) for i, s in enumerate(streams)]
    except json.JSONDecodeError:
        return []


def list_kfs_in_window_sec_frames(
    ctx: RuntimeContext, path: str, start_s: float, end_s: float, pad_s: float = DEFAULT_PAD_S
) -> list[float]:
    """Probe keyframes via frames (decode only the window)."""
    a = max(0.0, start_s - pad_s)
    dur = (end_s - start_s) + PAD_EDGE_MULTIPLIER * pad_s

    base = [
        *_QUIET,
        *_SELECT_STREAMS,
        "v:0",
        *_READ_INTERVALS,
        f"{a}%+{dur}",
        *_SKIP_NOKEY,
    ]
    entries = [
        (_SHOW_FRAMES, FRAME_BEST_EFFORT),
        (_SHOW_FRAMES, FRAME_PKT_PTS),
        (_SHOW_PACKETS, PACKET_PTS_FLAGS),
    ]
    approaches = [base + show + ["-show_entries", ent, *_CSV_OUTPUT, path] for show, ent in entries]
    for i, cmd in enumerate(approaches):
        out = run(ctx, cmd)
        if not out:
            continue
        kfs: list[float] = []
        for raw_line in out.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            t = _parse_kf_line(line, require_flag=i == FLAGGED_APPROACH_INDEX)
            if t is not None:
                kfs.append(t)
        if kfs:
            if ctx.verbosity >= Verbosity.COMMANDS:
                msg = (
                    f"Found {len(kfs)} keyframes using approach {i + 1} "
                    f"in window [{a:.1f}s, {a + dur:.1f}s]: "
                    f"{kfs[:MAX_DEBUG_KFS]}"
                    f"{'...' if len(kfs) > MAX_DEBUG_KFS else ''}"
                )
                emit_status(msg, status_callback=ctx.status_callback)
            return sorted(kfs)
    if ctx.verbosity >= Verbosity.COMMANDS:
        msg = f"No keyframes found in window [{a:.1f}s, {a + dur:.1f}s] with any approach"
        emit_status(msg, status_callback=ctx.status_callback)
    return []


def snap_window_copy_bounds(ctx: RuntimeContext, path: str, start_s: float, end_s: float) -> tuple[float, float]:
    """Snap start/end to keyframes within a window to avoid mid-GOP cuts."""
    pad = DEFAULT_PAD_S
    for _ in range(MAX_PAD_ATTEMPTS):
        kfs = list_kfs_in_window_sec_frames(ctx, path, start_s, end_s, pad_s=pad)
        if kfs:
            i = bisect.bisect_right(kfs, start_s) - 1
            i = max(i, 0)
            start_kf = kfs[i]

            j = bisect.bisect_right(kfs, end_s)
            if j > 0 and math.isclose(kfs[j - 1], end_s, abs_tol=1e-6):
                j -= 1
            if j >= len(kfs):
                j = len(kfs) - 1
            end_boundary = kfs[j]
            if end_boundary <= start_kf:
                end_boundary = start_kf + END_BOUNDARY_FALLBACK_DELTA
            return start_kf, end_boundary
        pad *= PAD_GROWTH_FACTOR
    return start_s, end_s


def _parse_kf_line(line: str, *, require_flag: bool) -> float | None:
    parts = line.split(",", 1)
    if require_flag and (len(parts) != EXPECTED_KF_PARTS or "K" not in parts[1]):
        return None
    try:
        return float(parts[0])
    except ValueError:
        return None


__all__ = [
    "RuntimeContext",
    "check_version",
    "clear_cache",
    "get_audio_bitrate",
    "get_audio_codec",
    "get_subtitle_tracks",
    "get_video_codec",
    "get_video_duration_sec",
    "list_kfs_in_window_sec_frames",
    "query",
    "run",
    "snap_window_copy_bounds",
]
