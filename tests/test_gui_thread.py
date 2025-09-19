from pathlib import Path
from typing import NoReturn

import pytest
from PyQt6.QtCore import QCoreApplication

from ffclipper.gui.controller import FFClipperController
from ffclipper.gui.ui_helpers import VideoProcessingThread
from ffclipper.models import Options


def test_thread_emits_failure_on_unexpected_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    QCoreApplication.instance() or QCoreApplication([])

    src = tmp_path / "in.mp4"
    src.write_text("data")

    def boom(*_args: object, **_kwargs: object) -> NoReturn:  # pragma: no cover - simple stub
        raise RuntimeError("boom")

    monkeypatch.setattr("ffclipper.gui.ui_helpers.run_conversion", boom)
    opts = Options(source=src)
    thread = VideoProcessingThread(opts)
    finished_payloads: list[dict] = []
    thread.finished.connect(finished_payloads.append)

    thread.run()

    assert finished_payloads == [{"success": False, "error": "Conversion failed: boom"}]


def test_controller_starts_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: C901
    QCoreApplication.instance() or QCoreApplication([])

    started: bool = False

    class DummySignal:
        def connect(self, _handler: object) -> None:  # pragma: no cover - simple stub
            pass

    class DummyThread:
        def __init__(self, options: Options, _status: object | None = None) -> None:
            self.options = options
            self.finished = DummySignal()

        def start(self) -> None:  # pragma: no cover - simple stub
            nonlocal started
            started = True

    class DummyGUI:
        def __init__(self, path: Path) -> None:
            self._path = path

        def collect_widget_values(self) -> dict[str, object]:
            return {"source": self._path}

        def validate_source(self) -> bool:
            return True

        def toggle_conversion_ui(self, *, converting: bool) -> None:  # pragma: no cover - simple stub
            pass

        def on_conversion_finished(self, _payload: dict) -> None:  # pragma: no cover - simple stub
            pass

        def show_error(self, message: str) -> None:  # pragma: no cover - simple stub
            raise AssertionError(message)

        def clear_status(self) -> None:  # pragma: no cover - simple stub
            pass

        def append_status(self, _msg: str) -> None:  # pragma: no cover - simple stub
            pass

    monkeypatch.setattr("ffclipper.gui.controller.VideoProcessingThread", DummyThread)

    src = tmp_path / "video.mp4"
    src.touch()
    controller = FFClipperController(DummyGUI(src))  # type: ignore[arg-type]
    controller.run()

    assert started is True
    assert isinstance(controller.processing_thread, DummyThread)
    assert controller.processing_thread.options.source == src
