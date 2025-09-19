"""GUI entry points and exported classes."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_run_gui_impl: Callable[[], None] | None = None
_IMPORT_ERROR: Exception | None = None
_IMPORT_TRACE = ""

try:  # pragma: no cover - import errors handled for runtime diagnostics
    from .controller import FFClipperController
    from .main_window import FFClipperGUI
    from .main_window import run_gui as run_gui_impl

    _run_gui_impl = run_gui_impl
except Exception as exc:  # pragma: no cover - avoid hiding failures behind pythonw  # noqa: BLE001
    FFClipperController = FFClipperGUI = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
    _IMPORT_TRACE = traceback.format_exc()
    # Best-effort: persist the import traceback to a log file so users can
    # diagnose startup issues even when running via pythonw / GUI launchers.
    try:  # Avoid importing project modules that may be the source of failure
        log_path = Path.home() / ".ffclipper" / "ffclipper.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n=== GUI import error ===\n")
            f.write(_IMPORT_TRACE)
            f.write("\n")
    except OSError:  # pragma: no cover - logging fallback
        # Ignore filesystem errors while attempting to persist the traceback.
        # We still surface the error via a message box or stderr below.
        pass

try:  # pragma: no cover - optional, used only for error display
    import tkinter as tk
    from tkinter import messagebox
except Exception:  # pragma: no cover - fall back to stderr  # noqa: BLE001
    tk = messagebox = None  # type: ignore[assignment]

__all__ = ["FFClipperController", "FFClipperGUI", "run_gui"]


def run_gui() -> None:
    """Launch the GUI application, surfacing startup errors."""
    if _run_gui_impl is not None:
        _run_gui_impl()
        return
    if _IMPORT_ERROR is None:
        raise RuntimeError("ffclipper GUI not available")
    if tk and messagebox:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ffclipper", _IMPORT_TRACE)
    else:
        sys.stderr.write(_IMPORT_TRACE)
    raise _IMPORT_ERROR
