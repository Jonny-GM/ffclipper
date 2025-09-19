"""Controller to manage option collection and conversion orchestration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtGui import QGuiApplication

from ffclipper.models import Options
from ffclipper.tools.cli import quote_arg

from .ui_helpers import VideoProcessingThread

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .main_window import FFClipperGUI


class FFClipperController:
    """Coordinate GUI actions with ffclipper."""

    def __init__(self, gui: FFClipperGUI) -> None:
        """Store reference to the GUI window."""
        self.gui = gui
        self.processing_thread: VideoProcessingThread | None = None
        self._cli_baseline = Options.defaults_for_gui()

    def get_options(self) -> Options:
        """Collect options from the GUI widgets."""
        opts_dict = self.gui.collect_widget_values()
        if opts_dict.get("source") is None:
            raise ValueError("source is required")
        return Options.model_validate(opts_dict)

    def run(self) -> None:
        """Start ffclipper in a background thread."""
        if not self.gui.validate_source():
            return
        try:
            # Start each action with a fresh status log
            self.gui.clear_status()
            self.gui.toggle_conversion_ui(converting=True)
            self.processing_thread = VideoProcessingThread(self.get_options(), self.gui.append_status)
            self.processing_thread.finished.connect(self.gui.on_conversion_finished)
            self.processing_thread.start()
        except (RuntimeError, ValueError) as e:
            logger.exception("Failed to start conversion thread")
            self.gui.show_error(f"Error starting conversion: {e}")
            self.gui.toggle_conversion_ui(converting=False)

    def build_cli_args(self, opts: Options) -> list[str]:
        """Return CLI args for ``opts`` using the shared Options serializer."""
        suppress_output = not self.gui.output_overridden
        return opts.to_cli_args(suppress_output=suppress_output, baseline=self._cli_baseline)

    def build_cli_command(self, opts: Options) -> str:
        """Return a shell-safe ffclipper command string for ``opts``."""
        parts = ["ffclipper", *self.build_cli_args(opts)]
        return " ".join(quote_arg(p) for p in parts)

    def copy_cli(self) -> None:
        """Copy the current ffclipper CLI command to the clipboard."""
        if not self.gui.validate_source():
            return
        try:
            # Clear previous output before showing new status
            self.gui.clear_status()
            opts = self.get_options()
            cmd = self.build_cli_command(opts)
            clipboard = QGuiApplication.clipboard()
            if clipboard is None:
                raise RuntimeError("Clipboard is not available")  # noqa: TRY301
            clipboard.setText(cmd)
            self.gui.append_status("Copied ffclipper command to clipboard")
        except (RuntimeError, ValueError) as e:  # error path
            logger.exception("Failed to build CLI command")
            self.gui.show_error(f"Error building CLI command: {e}")
