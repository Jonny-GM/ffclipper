"""Helper classes and mixins for building the GUI."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLayout,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ffclipper.backend import run_conversion

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

    from ffclipper.models import Options


class CollapsibleBox(QWidget):
    """Container with a toggle to expand or collapse its children."""

    def __init__(self, title: str, *, collapsed: bool = True) -> None:
        super().__init__()
        self._button = QToolButton()
        self._button.setText(title)
        self._button.setCheckable(True)
        self._button.setStyleSheet("QToolButton { border: none; }")
        self._button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._button.toggled.connect(self._toggle)
        self._button.setChecked(not collapsed)

        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content_layout = QVBoxLayout(self.content)

        frame = QGroupBox("")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 6, 8, 8)
        frame_layout.setSpacing(6)
        frame_layout.addWidget(self._button)
        frame_layout.addWidget(self.content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)

        self._toggle(self._button.isChecked())

    @pyqtSlot(bool)
    def _toggle(self, checked: bool) -> None:  # noqa: FBT001
        """Show or hide the content when the header button is toggled."""
        self.content.setVisible(checked)
        self._button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)


class LogEmitter(QObject):
    """Qt signal emitter that forwards log messages."""

    message = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    """Logging handler that emits records to a Qt signal."""

    def __init__(self, emitter: LogEmitter) -> None:
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a formatted log record to the associated signal."""
        msg = self.format(record)
        self.emitter.message.emit(msg)


class VideoProcessingThread(QThread):
    """Run the conversion process in a background thread."""

    finished = pyqtSignal(dict)
    status = pyqtSignal(str)

    def __init__(self, options: Options, status_callback: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self.options = options
        self._logger = logging.getLogger(__name__)
        if status_callback is not None:
            self.status.connect(status_callback)

    def run(self) -> None:  # pragma: no cover - thread behavior
        """Execute the conversion and emit status updates."""
        payload: dict
        try:
            _, result = run_conversion(self.options, status_callback=self.status.emit)
        except Exception as e:
            self._logger.exception("Unhandled error during conversion")
            msg = f"Conversion failed: {e}"
            payload = {"success": False, "error": msg}
        else:
            payload = asdict(result)
        finally:
            self.finished.emit(payload)


NOT_NONE = object()


class UIHelpers:
    """Mixin providing convenience methods for building the UI."""

    widgets: dict[str, tuple[QWidget, Callable[[QWidget], object], object]]
    control_rules: dict[object, list[tuple[str, object]]]
    layout: QVBoxLayout

    def create_field(self, placeholder: str = "", *, readonly: bool = False) -> QLineEdit:
        """Return a line edit with optional placeholder and read-only state."""
        field = QLineEdit()
        if placeholder:
            field.setPlaceholderText(placeholder)
        field.setReadOnly(readonly)
        field.textChanged.connect(lambda _text: self.on_settings_changed())
        return field

    def create_combo(self, items: list[str], current: str | None = None) -> QComboBox:
        """Return a combo box populated with ``items``."""
        combo = QComboBox()
        combo.addItems(items)
        if current:
            combo.setCurrentText(current)
        combo.currentIndexChanged.connect(lambda _idx: self.on_settings_changed())
        return combo

    def create_spinbox(self, min_val: int, max_val: int, value: int) -> QSpinBox:
        """Return a spin box with the specified range and value."""
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(value)
        spin.valueChanged.connect(lambda _val: self.on_settings_changed())
        return spin

    def add_group(
        self,
        title: str,
        layout_cls: type[QLayout] | None = None,
        *,
        collapsible: bool = False,
        collapsed: bool = False,
    ) -> QLayout:
        """Add a titled group and return its layout.

        By default a ``QGroupBox`` is used. When ``collapsible`` is ``True`` a
        :class:`CollapsibleBox`` is created instead and ``collapsed`` controls
        its initial state.
        """
        layout = (layout_cls or QVBoxLayout)()
        if collapsible:
            group = CollapsibleBox(title, collapsed=collapsed)
            group.content_layout.addLayout(layout)
            self.layout.addWidget(group)  # type: ignore[attr-defined]
            return layout
        group = QGroupBox(title)
        group.setLayout(layout)
        self.layout.addWidget(group)  # type: ignore[attr-defined]
        return layout

    def add_checkbox(self, text: str, *, checked: bool = False) -> QCheckBox:
        """Return a checkbox with optional default state."""
        c = QCheckBox(text)
        c.setChecked(checked)
        c.toggled.connect(self.on_settings_changed)
        return c

    def register_widget(
        self,
        name: str,
        widget: QWidget,
        extractor: Callable[[QWidget], object],
        default: object | None = None,
    ) -> None:
        """Register a widget for option extraction.

        If ``default`` is not provided, the current widget value is used.
        """
        if default is None:
            default = extractor(widget)
        self.widgets[name] = (widget, extractor, default)

    def add_control_rule(self, widgets: QWidget | tuple[QWidget, ...], rules: list[tuple[str, object]]) -> None:
        """Associate widgets with values that enable them."""
        self.control_rules[widgets] = rules

    def apply_control_rules(self, values: dict[str, object]) -> None:
        """Enable or disable widgets based on control rules."""

        def lookup(path: str) -> object | None:
            current: object = values
            for part in path.split("."):
                if not isinstance(current, dict):
                    return None
                current = current.get(part)  # type: ignore[assignment]
                if current is None:
                    return None
            return current

        for widgets, rules in self.control_rules.items():
            enabled = all((lookup(key) is not None) if val is NOT_NONE else (lookup(key) == val) for key, val in rules)
            if isinstance(widgets, QWidget):
                widgets.setEnabled(enabled)
            else:
                for w in widgets:
                    w.setEnabled(enabled)
