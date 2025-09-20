"""Application icon helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPixmap

if TYPE_CHECKING:
    from collections.abc import Iterable

EMOJI_CLAPPER_BOARD = "\U0001f3ac"
FALLBACK_TEXT = "FF"
_ICON_SIZES: tuple[int, ...] = (16, 24, 32, 64, 128, 256)
_GLYPH_SCALE = 0.82
_PREFERRED_EMOJI_FONTS: tuple[str, ...] = (
    "Segoe UI Emoji",
    "Apple Color Emoji",
    "Noto Color Emoji",
    "Noto Emoji",
)


def _supports_glyph(font: QFont, glyph: str) -> bool:
    """Return True when ``font`` can render ``glyph``."""
    return QFontMetrics(font).inFontUcs4(ord(glyph))


def _pick_emoji_font(preferred: Iterable[str]) -> QFont | None:
    """Return an emoji-capable font, preferring the provided family names."""
    families = tuple(QFontDatabase.families())
    ordered = [name for name in preferred if name in families]
    ordered.extend(name for name in families if name not in ordered)
    for family in ordered:
        font = QFont(family)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        if _supports_glyph(font, EMOJI_CLAPPER_BOARD):
            return font
    return None


def _fallback_font() -> QFont:
    """Return a bold system font suitable for drawing fallback text."""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setWeight(QFont.Weight.Bold)
    return font


def _paint_pixmap(size: int, font: QFont, text: str, *, solid_bg: bool) -> QPixmap:
    """Draw ``text`` centered in a square pixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if solid_bg:
        painter.fillRect(pixmap.rect(), Qt.GlobalColor.black)
        painter.setPen(Qt.GlobalColor.white)
    sized_font = QFont(font)
    sized_font.setPixelSize(int(size * _GLYPH_SCALE))
    painter.setFont(sized_font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pixmap


@lru_cache(maxsize=1)
def build_app_icon() -> QIcon:
    """Create a multi-resolution application icon."""
    icon = QIcon()
    font = _pick_emoji_font(_PREFERRED_EMOJI_FONTS)
    text = EMOJI_CLAPPER_BOARD if font is not None else FALLBACK_TEXT
    if font is None:
        font = _fallback_font()
    solid_bg = text == FALLBACK_TEXT
    for size in _ICON_SIZES:
        pixmap = _paint_pixmap(size, font, text, solid_bg=solid_bg)
        icon.addPixmap(pixmap, QIcon.Mode.Normal, QIcon.State.Off)
    return icon
