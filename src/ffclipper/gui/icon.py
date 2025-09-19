"""Application icon helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

EMOJI_CLAPPER_BOARD = "\U0001f3ac"
_ICON_SIZES: tuple[int, ...] = (16, 24, 32, 64, 128, 256)
_GLYPH_SCALE = 0.82
_PREFERRED_EMOJI_FONTS: tuple[str, ...] = (
    "Segoe UI Emoji",
    "Apple Color Emoji",
    "Noto Color Emoji",
    "Noto Emoji",
)


def _supports_clapper(font: QFont) -> bool:
    """Return True if the font can render the clapper board emoji."""
    return QFontMetrics(font).inFontUcs4(ord(EMOJI_CLAPPER_BOARD))


def _pick_font(preferred: Iterable[str]) -> QFont:
    """Choose the first available emoji-aware font, falling back to a generic one."""
    families = tuple(QFontDatabase.families())
    ordered = [name for name in preferred if name in families]
    ordered.extend(name for name in families if name not in ordered)
    for family in ordered:
        font = QFont(family)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        if _supports_clapper(font):
            return font
    fallback = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    fallback.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return fallback if _supports_clapper(fallback) else QFont()


@lru_cache(maxsize=1)
def build_app_icon() -> QIcon:
    """Create a multi-resolution application icon featuring the clapper board emoji."""
    icon = QIcon()
    font = _pick_font(_PREFERRED_EMOJI_FONTS)
    for size in _ICON_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        sized_font = QFont(font)
        sized_font.setPixelSize(int(size * _GLYPH_SCALE))
        painter.setFont(sized_font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, EMOJI_CLAPPER_BOARD)
        painter.end()
        icon.addPixmap(pixmap, QIcon.Mode.Normal, QIcon.State.Off)
    return icon
