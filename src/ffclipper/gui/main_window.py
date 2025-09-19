"""Main application window and helpers for the GUI."""

from __future__ import annotations

import logging
import sys
from contextlib import suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from collections.abc import Callable
    from types import TracebackType

    from PyQt6.QtWidgets import QWidget


from ffclipper.models import RuntimeContext
from ffclipper.models.options import DEFAULT_CONTAINER, Options
from ffclipper.models.plan import derive_output_path
from ffclipper.models.types import Container
from ffclipper.models.verbosity import Verbosity
from ffclipper.tools import get_ffmpeg_version, probe

from .controller import FFClipperController
from .declarative_ui import build_ui
from .icon import build_app_icon
from .ui_helpers import LogEmitter, QtLogHandler, UIHelpers

VIDEO_FILE_FILTER = "Video files (*.mkv *.mp4 *.avi *.mov *.webm *.m4v *.wmv *.flv);;All files (*)"

logger = logging.getLogger(__name__)


def _ensure_log_file_handler() -> None:
    """Attach a rotating file handler to the root logger."""
    try:
        lf = Path.home() / ".ffclipper" / "ffclipper.log"
        lf.parent.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        exists = any(
            isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", None) and Path(h.baseFilename) == lf
            for h in root.handlers
        )
        if not exists:
            fh = RotatingFileHandler(lf, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            root.addHandler(fh)
    except OSError:  # pragma: no cover - best effort
        pass


class FFClipperGUI(QMainWindow, UIHelpers):
    """Window managing FFClipper controls."""

    layout: QVBoxLayout
    source: QLineEdit
    run_btn: QPushButton
    status_text: QTextEdit
    progress_bar: QProgressBar
    # Trim mode combo is created in declarative_ui
    trim_mode_combo: QComboBox  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ffclipper")
        self.setGeometry(100, 100, 600, 700)
        self.widgets: dict[str, tuple[QWidget, Callable[[QWidget], object], object]] = {}
        self.control_rules: dict[object, list[tuple[str, bool]]] = {}
        # Initialize autofill state before UI signals may fire during build_ui
        self._last_autofill_value: str | None = None
        self.output_overridden = False
        self._ui_ready = False
        self.controller = FFClipperController(self)
        build_ui(self)
        # Wire trim mode selector if present and set initial state
        with suppress(AttributeError):
            self.trim_mode_combo.currentIndexChanged.connect(lambda _i: self.on_trim_mode_changed())
        # UI built and signal wiring is complete; enable reactive handlers.
        self._ui_ready = True
        self._setup_logging()
        # Initialize trim mode after widgets all exist
        self.init_trim_mode_from_state()
        self.on_settings_changed()
        self._init_versions()

    def _setup_logging(self) -> None:
        """Configure logging to the GUI and a rotating log file.

        - Root logger: set to DEBUG so file logging captures everything.
        - File handler: Rotating at ``~/.ffclipper/ffclipper.log``.
        - Qt handler: mirrors messages into the status pane; starts at WARNING
          and is adjusted based on UI verbosity.
        """
        _ensure_log_file_handler()
        emitter = LogEmitter()
        emitter.message.connect(self.append_status)
        handler = QtLogHandler(emitter)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        handler.setLevel(logging.WARNING)
        logging.getLogger().addHandler(handler)
        self._log_emitter = emitter
        self._qt_handler = handler  # type: ignore[attr-defined]

    def _init_versions(self) -> None:
        """Check for FFmpeg tools and display their versions."""
        try:
            get_ffmpeg_version()
            with RuntimeContext() as ctx:
                probe.check_version(ctx)
        except (OSError, RuntimeError) as e:  # error path
            QMessageBox.critical(self, "Error", str(e))
            self.setEnabled(False)

    def browse_file(self) -> None:
        """Select a source video file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "", VIDEO_FILE_FILTER)
        if file_path:
            # Ensure native separators for consistent display on Windows
            self.source.setText(QDir.toNativeSeparators(file_path))

    def collect_widget_values(self, *, include_disabled: bool = False) -> dict[str, object]:
        """Return current widget values as a nested mapping."""
        values: dict[str, object] = {}
        for name, (widget, extractor, _default) in self.widgets.items():
            if not include_disabled and not widget.isEnabled():
                continue
            value = extractor(widget)
            parts = name.split(".")
            target: dict[str, object] = values
            for part in parts[:-1]:
                target = target.setdefault(part, {})  # type: ignore[assignment]
            target[parts[-1]] = value
        return values

    def on_settings_changed(self) -> None:
        """React to updates of any UI controls."""
        values = self.collect_widget_values(include_disabled=True)
        self.apply_control_rules(values)
        level = values.get("runtime", {}).get("verbosity", 0)
        # Keep root at DEBUG for file logs; adjust Qt handler only.
        qt_level = (
            logging.DEBUG
            if level >= Verbosity.OUTPUT
            else logging.INFO
            if level >= Verbosity.COMMANDS
            else logging.WARNING
        )
        with suppress(AttributeError):  # handler may not be attached yet
            self._qt_handler.setLevel(qt_level)  # type: ignore[attr-defined]
        # Update auto-fill if appropriate when settings change from non-output fields.
        self._autofill_on_change()

    def on_trim_mode_changed(self) -> None:
        """Enable either End or Duration input based on selected mode."""
        # Resolve widgets for end and duration
        end_w = self.widgets.get("time.end", (None, None, None))[0]
        dur_w = self.widgets.get("time.duration", (None, None, None))[0]
        if end_w is None or dur_w is None:
            return
        # If unified control is used, both names map to the same widget.
        if end_w is dur_w:
            """Unified End/Duration control already manages placeholder and reset."""
            with suppress(AttributeError):
                if hasattr(dur_w, "setText"):
                    dur_w.setText("")
            self.on_settings_changed()
            return
        use_duration = False
        with suppress(AttributeError):
            use_duration = self.trim_mode_combo.currentText() == "Duration"
        if use_duration:
            dur_w.setEnabled(True)
            end_w.setEnabled(False)
            if hasattr(end_w, "setText"):
                end_w.setText("")
        else:
            end_w.setEnabled(True)
            dur_w.setEnabled(False)
            if hasattr(dur_w, "setText"):
                dur_w.setText("")
        # Apply any dependent control rules
        self.on_settings_changed()

    def init_trim_mode_from_state(self) -> None:
        """Set initial enabled/disabled state for trim fields from radios."""
        # Trigger handler to reflect current radio selection; tolerant if radios missing
        with suppress(AttributeError):
            self.on_trim_mode_changed()

    def validate_source(self) -> bool:
        """Ensure a source file path or URL has been provided."""
        if not self.source.text():
            QMessageBox.warning(self, "Warning", "Please select a video file or enter a URL first.")
            return False
        return True

    def append_status(self, message: str) -> None:
        """Append a status line to the status box."""
        self.status_text.append(message)
        self.status_text.ensureCursorVisible()

    def clear_status(self) -> None:
        """Clear the status text box."""
        self.status_text.clear()

    def toggle_conversion_ui(self, *, converting: bool) -> None:
        """Enable or disable controls during conversion."""
        self.run_btn.setEnabled(not converting)
        self.progress_bar.setVisible(converting)
        if converting:
            self.progress_bar.setRange(0, 0)

    def show_error(self, message: str) -> None:
        """Display an error dialog."""
        QMessageBox.critical(self, "Error", message)

    def on_conversion_finished(self, result: dict) -> None:
        """Handle completion of the conversion thread."""
        self.toggle_conversion_ui(converting=False)
        if not result["success"]:
            self.show_error(result["error"] or "Conversion failed")

    def _setup_output_autofill(self) -> None:
        """Handle wiring declaratively in ``declarative_ui``."""
        return

    def _current_container(self) -> Container:
        text = self.container.currentText() or DEFAULT_CONTAINER.value
        try:
            return Container(text)
        except ValueError:
            return DEFAULT_CONTAINER

    def _derive_from_widgets(self) -> str | None:
        src = self.source.text().strip()
        if not src:
            return None
        # Validate source is acceptable (existing file or http/https URL)
        try:
            # Reuse Options' source validator to avoid duplicating rules.
            _ = Options.validate_source(src)  # type: ignore[arg-type]
        except ValueError:
            return None
        try:
            path = derive_output_path(src, None, self._current_container())
        except ValueError:
            return None
        return str(path)

    def _autofill_on_change(self) -> None:
        """Update output if auto-managed, avoiding changes while user is typing."""
        if not self._ui_ready:
            return
        output_field = self.output
        # Do not auto-fill while the user is focused in the output field.
        if output_field.hasFocus():
            return
        derived = self._derive_from_widgets()
        if derived is None:
            # Clear output if we were auto-managing and current matches last auto-fill (or is empty)
            current = output_field.text().strip()
            if not self.output_overridden and (current == (self._last_autofill_value or "") or not current):
                self._last_autofill_value = None
                output_field.setText("")
            return
        current = output_field.text().strip()
        if not current:
            # Empty output -> always fill with derived
            self._last_autofill_value = derived
            self.output_overridden = False
            output_field.setText(derived)
            return
        # If output hasn't been overridden and still matches the last derived value, update it
        if not self.output_overridden and current == (self._last_autofill_value or ""):
            self._last_autofill_value = derived
            output_field.setText(derived)

    def on_output_editing_finished(self) -> None:
        """Handle user finishing edits to the output field.

        - If left empty, auto-derive and keep auto mode.
        - If equals the derived suggestion, keep auto mode.
        - Otherwise, mark as user-overridden and stop auto updates.
        """
        output_field = self.output
        current = output_field.text().strip()
        derived = self._derive_from_widgets()
        if not current:
            if derived is not None:
                self._last_autofill_value = derived
                self.output_overridden = False
                output_field.setText(derived)
            return
        if derived is not None and current == derived:
            self._last_autofill_value = derived
            self.output_overridden = False
        else:
            # User entered a custom path
            self.output_overridden = True

        # If user supplied an explicit output with a known extension, update
        # the Container dropdown to match for consistency.
        self._sync_container_from_output(current)

    def on_output_text_changed(self, text: str) -> None:
        """Keep container dropdown in sync while typing a valid extension."""
        self._sync_container_from_output(text)

    def on_container_changed(self) -> None:
        """React to container changes by fixing output suffix and auto-filling.

        - If output is empty and auto-managed, auto-fill will populate it.
        - If output has an invalid or mismatched extension, replace just the
          extension to match the selected container, even if overridden.
        """
        self._maybe_fix_output_suffix()
        self._autofill_on_change()

    def _sync_container_from_output(self, output_path: str) -> None:
        """Update container dropdown to match the output file extension."""
        suffix = Path(output_path).suffix.lstrip(".").lower()
        if not suffix:
            return
        try:
            inferred = Container(suffix)
        except ValueError:
            return  # Unrecognized extension; don't change container
        if self.container.currentText() != inferred.value:
            self.container.setCurrentText(inferred.value)

    def _maybe_fix_output_suffix(self) -> None:
        """Ensure the output path's extension matches the selected container.

        If the current output has no extension, or has an unrecognized/mismatched
        extension, update only the suffix to the selected container's extension.
        """
        output_field = self.output
        current = output_field.text().strip()
        if not current:
            return
        selected = self._current_container()
        p = Path(current)
        suffix = p.suffix.lstrip(".").lower()
        needs_change = False
        if not suffix:
            needs_change = True
        else:
            try:
                inferred = Container(suffix)
            except ValueError:
                needs_change = True  # invalid extension -> fix it
            else:
                if inferred != selected:
                    needs_change = True  # mismatched -> align with selection
        if needs_change:
            try:
                updated = str(p.with_suffix(selected.extension))
            except ValueError:
                return
            if updated != current:
                output_field.setText(updated)


def run_gui() -> None:
    """Launch the GUI application."""
    try:
        # Ensure early exceptions get written to the log file as well.
        _ensure_log_file_handler()

        # Log uncaught exceptions to the file handler too.

        def _excepthook(
            exc_type: type[BaseException],
            exc_value: BaseException,
            exc_traceback: TracebackType | None,
        ) -> None:
            if issubclass(exc_type, KeyboardInterrupt):  # allow normal interrupt
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logging.getLogger(__name__).exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

        sys.excepthook = _excepthook

        app = QApplication(sys.argv)
        app.setApplicationName("ffclipper")
        app.setOrganizationName("ffclipper")
        icon = build_app_icon()
        app.setWindowIcon(icon)
        window = FFClipperGUI()
        window.setWindowIcon(icon)
        window.show()
        sys.exit(app.exec())
    except Exception:  # pragma: no cover - display startup errors
        logger.exception("Failed to launch GUI")
        raise


if __name__ == "__main__":  # pragma: no cover - manual execution
    run_gui()
