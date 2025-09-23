"""Build GUI sections automatically from CLI options."""

from __future__ import annotations

import importlib
from enum import Enum, IntEnum
from pathlib import Path
from types import UnionType
from typing import TYPE_CHECKING, Annotated, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel
from pydantic_core import PydanticUndefined
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ffclipper.gui.ui_helpers import NOT_NONE
from ffclipper.models.annotations import EnableWhen, FieldLabel
from ffclipper.models.options import Options

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from pydantic.fields import FieldInfo
    from PyQt6.QtGui import QIcon

    from .main_window import FFClipperGUI


def build_ui(window: FFClipperGUI) -> None:
    """Construct the main window layout from ``Options``."""
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    window.layout = QVBoxLayout(central_widget)  # type: ignore[assignment]

    title = QLabel("ffclipper")
    title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    window.layout.addWidget(title)

    defaults = _default_options()
    _build_from_model(window, Options, defaults)
    _build_bottom(window)


# Groups rendered as collapsible sections in the GUI (other than "Output")
COLLAPSIBLE_GROUPS = {"Audio", "Video", "Subtitles", "Runtime"}


def _default_options() -> Options:
    """Return ``Options`` pre-populated for the GUI without validation."""
    return Options.defaults_for_gui()


def _build_from_model(window: FFClipperGUI, model_cls: type[BaseModel], defaults: BaseModel) -> None:
    hints = get_type_hints(model_cls, include_extras=True)
    groups: dict[str, tuple[QGridLayout, int]] = {}
    for name, annotation in hints.items():
        if name not in model_cls.model_fields:
            # Skip ClassVar or other non-model attributes
            continue
        field = model_cls.model_fields[name]
        base_type, optional, extras = _resolve(annotation)
        group = _group_name(base_type, extras)
        default_val = getattr(defaults, name, PydanticUndefined)
        if group in groups:
            layout, row = groups[group]
        else:
            layout = window.add_group(
                group,
                QGridLayout,
                collapsible=group in COLLAPSIBLE_GROUPS,
                collapsed=group in COLLAPSIBLE_GROUPS,
            )
            if not isinstance(layout, QGridLayout):  # pragma: no cover - defensive
                raise TypeError("Expected QGridLayout")
            row = 0
        if _is_model(base_type):
            # Narrow for type-checkers without using cast or asserts
            if isinstance(base_type, type) and issubclass(base_type, BaseModel):
                model_type = base_type
            else:  # pragma: no cover - defensive fallback
                raise TypeError("Expected BaseModel subclass")
            row = _build_model(
                window,
                model_type,
                layout,
                prefix=name,
                row=row,
                defaults=default_val,
            )
        else:
            cfg = FieldConfig()
            cfg.full_name = name
            cfg.typ = base_type
            cfg.optional = optional
            cfg.field = field
            cfg.default_val = default_val
            cfg.extras = extras
            _add_field(window, layout, row, cfg)
            row += 1
        groups[group] = (layout, row)


def _build_model(  # noqa: PLR0913
    window: FFClipperGUI,
    model_cls: type[BaseModel],
    layout: QGridLayout,
    prefix: str,
    *,
    row: int,
    defaults: BaseModel | object,
) -> int:
    hints = get_type_hints(model_cls, include_extras=True)
    # For Time selection: collect End/Duration to render a unified control later.
    collect_time = prefix == "time"
    end_field_info = None
    dur_field_info = None
    default_end_val: object = PydanticUndefined
    default_dur_val: object = PydanticUndefined
    for name, annotation in hints.items():
        if name not in model_cls.model_fields:
            # Skip ClassVar or other non-model attributes
            continue
        field = model_cls.model_fields[name]
        base_type, optional, extras = _resolve(annotation)
        full = f"{prefix}.{name}"
        default_val = (
            getattr(defaults, name, PydanticUndefined) if isinstance(defaults, BaseModel) else PydanticUndefined
        )
        if collect_time and name in {"end", "duration"}:
            if name == "end":
                end_field_info = field
                default_end_val = default_val
            else:
                dur_field_info = field
                default_dur_val = default_val
            continue
        if _is_model(base_type):
            if isinstance(base_type, type) and issubclass(base_type, BaseModel):
                model_type = base_type
            else:  # pragma: no cover - defensive fallback
                raise TypeError("Expected BaseModel subclass")
            row = _build_model(
                window,
                model_type,
                layout,
                full,
                row=row,
                defaults=default_val,
            )
        else:
            cfg = FieldConfig()
            cfg.full_name = full
            cfg.typ = base_type
            cfg.optional = optional
            cfg.field = field
            cfg.default_val = default_val
            cfg.extras = extras
            _add_field(window, layout, row, cfg)
            row += 1
    if collect_time and end_field_info is not None and dur_field_info is not None:
        end_desc = getattr(end_field_info, "description", "") or "End timestamp for the clip."
        dur_desc = getattr(dur_field_info, "description", "") or "Desired duration of the output clip."
        row = _add_time_unified_control(
            window,
            layout,
            row,
            end_desc=end_desc,
            dur_desc=dur_desc,
            default_end=default_end_val,
            default_dur=default_dur_val,
        )
    return row


def _resolve(annotation: object) -> tuple[object, bool, list[object]]:
    extras: list[object] = []
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *extras = get_args(annotation)
        annotation = base
        origin = get_origin(annotation)
    optional = False
    if origin in (Union, UnionType) and type(None) in get_args(annotation):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            annotation = args[0]
            optional = True
    return annotation, optional, extras


def _group_name(annotation: object, extras: list[object]) -> str:
    for extra in extras:
        grp = getattr(extra, "group", None)
        if grp:
            return grp[0]._name  # noqa: SLF001
    if _is_model(annotation):
        cfg = getattr(annotation, "__cyclopts__", None)
        if cfg and cfg.parameters and cfg.parameters[0].group:
            return cfg.parameters[0].group[0]._name  # noqa: SLF001
    return "Parameters"


def _is_model(annotation: object) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _label(name: str) -> str:
    return name.replace("_", " ").title()


def _assign_attr(window: FFClipperGUI, full_name: str, widget: QWidget) -> None:
    """Expose widgets on ``window`` using underscored option names."""
    setattr(window, full_name.replace(".", "_"), widget)


class FieldConfig:
    """Configuration for rendering a single field in the GUI.

    Attributes:
        full_name: Dotted path for the field (e.g., "video.codec").
        typ: The field's resolved type.
        optional: Whether the field allows ``None``.
        field: The original Pydantic field information.
        default_val: The default value from the model or ``PydanticUndefined``.
        extras: Any ``Annotated`` extras attached to the field.

    """

    # Attributes are assigned by the callers to avoid a long __init__.
    full_name: str
    typ: object
    optional: bool
    field: FieldInfo
    default_val: object
    extras: list[object]

    @property
    def name(self) -> str:
        """Return the simple field name (without prefixes)."""
        return self.full_name.split(".")[-1]

    @property
    def label(self) -> str:
        """Return a human-friendly label for the field name."""
        override = next(
            (extra.text for extra in self.extras if isinstance(extra, FieldLabel)),
            None,
        )
        if override:
            return override
        return _label(self.name)

    @property
    def tooltip(self) -> str:
        """Return the tooltip from the field description if present."""
        return self.field.description or ""


def _effective_default(field: FieldInfo, default_val: object) -> object:
    """Resolve the effective default considering Pydantic's undefined.

    Prefers an explicit default value passed in, then the field's own default,
    and finally ``None`` if neither is defined.
    """
    default = default_val
    if default is PydanticUndefined:
        default = field.default
    if default is PydanticUndefined:
        return None
    return default


def _extract_rules(extras: list[object]) -> list[tuple[str, object]]:
    """Build control rules from ``EnableWhen`` annotations."""
    return [
        (extra.key, NOT_NONE if extra.not_none else extra.value) for extra in extras if isinstance(extra, EnableWhen)
    ]


def _create_widget(
    window: FFClipperGUI, cfg: FieldConfig, default: object
) -> tuple[QWidget, Callable[[QWidget], object], object]:
    """Create a widget for the field and return (widget, extractor, default_for_register)."""
    typ = cfg.typ
    if typ is bool:
        return _create_bool_widget(window, cfg, default)

    normalized_default = default.value if isinstance(default, Enum) else default
    if isinstance(typ, type) and issubclass(typ, Enum):
        return _create_enum_widget(window, cfg, normalized_default, typ)
    if typ is int and not cfg.optional:
        return _create_int_spinbox_widget(window, cfg, normalized_default)
    return _create_line_edit_widget(window, cfg, normalized_default)


def _create_bool_widget(
    window: FFClipperGUI, cfg: FieldConfig, default: object
) -> tuple[QWidget, Callable[[QWidget], object], object]:
    widget = window.add_checkbox(cfg.label, checked=bool(default))

    def extractor(_w: QWidget) -> object:
        return widget.isChecked()

    if cfg.tooltip:
        widget.setToolTip(cfg.tooltip)
    return widget, extractor, default


def _create_enum_widget(
    window: FFClipperGUI, cfg: FieldConfig, normalized_default: object, enum_type: type[Enum]
) -> tuple[QWidget, Callable[[QWidget], object], object]:
    # Present IntEnum choices by name (e.g., QUIET/COMMANDS/OUTPUT), others by value.
    is_int = issubclass(enum_type, IntEnum)
    items = [e.name for e in enum_type] if is_int else [str(e.value) for e in enum_type]

    if cfg.optional and normalized_default is None:
        items.insert(0, "")

    # Determine current selection from default
    if is_int:
        current: str
        try:
            member = (
                normalized_default
                if isinstance(normalized_default, enum_type)  # type: ignore[arg-type]
                else enum_type(normalized_default)  # type: ignore[arg-type]
            )
            current = member.name if isinstance(member, enum_type) else ""  # type: ignore[arg-type]
        except (ValueError, TypeError):
            current = ""
    else:
        current = str(normalized_default) if normalized_default is not None else ""

    widget = window.create_combo(items, current if current else None)

    def extractor(_w: QWidget) -> object:
        text = widget.currentText()
        if cfg.optional and not text:
            return None
        return enum_type[text] if is_int else enum_type(text)

    if cfg.tooltip:
        widget.setToolTip(cfg.tooltip)
    if cfg.full_name == "container":
        widget.currentIndexChanged.connect(lambda _i: window.on_container_changed())
    return widget, extractor, normalized_default


def _create_int_spinbox_widget(
    window: FFClipperGUI, cfg: FieldConfig, normalized_default: object
) -> tuple[QWidget, Callable[[QWidget], object], object]:
    initial = normalized_default if isinstance(normalized_default, int) else 0
    widget = window.create_spinbox(-1000000, 1000000, initial)

    def extractor(_w: QWidget) -> object:
        return widget.value()

    if cfg.tooltip:
        widget.setToolTip(cfg.tooltip)
    return widget, extractor, normalized_default


def _create_line_edit_widget(
    window: FFClipperGUI, cfg: FieldConfig, normalized_default: object
) -> tuple[QWidget, Callable[[QWidget], object], object]:
    widget = window.create_field(cfg.field.description or "")
    if normalized_default is not None:
        widget.setText(str(normalized_default))

    if cfg.typ is int:

        def extractor(_w: QWidget) -> object:
            txt = widget.text()
            return int(txt) if txt else None
    else:

        def extractor(_w: QWidget) -> object:
            return widget.text().strip() or None

    if cfg.full_name == "output":
        widget.textChanged.connect(window.on_output_text_changed)
        widget.editingFinished.connect(window.on_output_editing_finished)
    return widget, extractor, normalized_default


def _place_widget(window: FFClipperGUI, layout: QGridLayout, row: int, cfg: FieldConfig, widget: QWidget) -> None:
    """Place the widget in the grid with labels and special cases."""
    tooltip = cfg.tooltip
    # Booleans span two columns without a label.
    if cfg.typ is bool:
        layout.addWidget(widget, row, 0, 1, 2)
        return

    label = QLabel(f"{cfg.label}:")
    if tooltip:
        label.setToolTip(tooltip)
        widget.setToolTip(tooltip)

    if cfg.full_name == "source":
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(window.browse_file)
        layout.addWidget(label, row, 0)
        layout.addWidget(widget, row, 1)
        layout.addWidget(browse_btn, row, 2)
        return

    if cfg.full_name == "container":
        # Place to the right of Output on the previous row.
        target_row = max(row - 1, 0)
        layout.addWidget(label, target_row, 2)
        layout.addWidget(widget, target_row, 3)
        layout.setColumnStretch(1, 4)
        layout.setColumnStretch(3, 1)
        return

    # Default labeled placement.
    layout.addWidget(label, row, 0)
    layout.addWidget(widget, row, 1)


def _register(
    window: FFClipperGUI,
    cfg: FieldConfig,
    widget: QWidget,
    extractor: Callable[[QWidget], object],
    default_for_register: object,
) -> None:
    """Register widget with the window and wire any control rules."""
    window.register_widget(cfg.full_name, widget, extractor, default_for_register)
    _assign_attr(window, cfg.full_name, widget)
    rules = _extract_rules(cfg.extras)
    if rules:
        window.add_control_rule(widget, rules)


def _add_field(
    window: FFClipperGUI,
    layout: QGridLayout,
    row: int,
    cfg: FieldConfig,
) -> None:
    """Render and register a single field row in the form."""
    default = _effective_default(cfg.field, cfg.default_val)
    widget, extractor, reg_default = _create_widget(window, cfg, default)
    _place_widget(window, layout, row, cfg, widget)
    _register(window, cfg, widget, extractor, reg_default)


def _add_time_unified_control(  # noqa: PLR0913
    window: FFClipperGUI,
    layout: QGridLayout,
    row: int,
    *,
    end_desc: str,
    dur_desc: str,
    default_end: object,
    default_dur: object,
) -> int:
    """Add a single input with an inline mode dropdown on the label.

    The dropdown chooses between interpreting the input as End or Duration.
    """
    # Use the mode selector as the label itself (no extra text)
    mode = window.create_combo(["Duration", "End"], current="Duration")

    # Single text input
    field = window.create_field(dur_desc or "")

    # Initialize from defaults
    current_mode = "Duration"
    initial_text = ""
    if isinstance(default_dur, str) and default_dur:
        current_mode = "Duration"
        initial_text = default_dur
    elif isinstance(default_end, str) and default_end:
        current_mode = "End"
        initial_text = default_end
    mode.setCurrentText(current_mode)
    if initial_text:
        field.setText(initial_text)

    # Place widgets: dropdown in label column, input in value column
    layout.addWidget(mode, row, 0)
    layout.addWidget(field, row, 1)

    # Expose to main window for change handling
    window.trim_mode_combo = mode  # type: ignore[attr-defined]
    window.trim_value_field = field  # type: ignore[attr-defined]

    # Keep placeholder and tooltips in sync
    def _sync_desc() -> None:
        desc = dur_desc if mode.currentText() == "Duration" else end_desc
        field.setPlaceholderText(desc)
        mode.setToolTip(desc)
        field.setToolTip(desc)

    mode.currentIndexChanged.connect(lambda _i: (_sync_desc(), field.setText("")))
    _sync_desc()

    # Register logical fields with conditional extractors
    def extract_end(_w: QWidget) -> object:
        txt = field.text().strip()
        return txt if mode.currentText() == "End" and txt else None

    def extract_dur(_w: QWidget) -> object:
        txt = field.text().strip()
        return txt if mode.currentText() == "Duration" and txt else None

    window.register_widget("time.end", field, extract_end, default_end)
    window.register_widget("time.duration", field, extract_dur, default_dur)

    return row + 1


def _load_icon(name: str) -> QIcon | None:
    """Return a QIcon loaded from the local icons folder, or None.

    Uses dynamic import so tests don't require full Qt GUI bindings at import time.
    """
    try:  # pragma: no cover - environment dependent
        qtgui = importlib.import_module("PyQt6.QtGui")
    except ImportError:  # pragma: no cover - icon optional
        return None
    qicon_cls = getattr(qtgui, "QIcon", None)
    if qicon_cls is None:
        return None
    icon_path = Path(__file__).with_name("icons") / name
    if icon_path.is_file():
        return qicon_cls(str(icon_path))
    return None


def _apply_icon(btn: QPushButton, name: str) -> None:
    """Apply a bundled icon to a button; skip silently if unavailable."""
    icon = _load_icon(name)
    if icon is None:
        return
    btn.setIcon(icon)


def _build_bottom(window: FFClipperGUI) -> None:
    button_layout = QHBoxLayout()

    # Copy button
    copy_btn = QPushButton()
    copy_btn.setToolTip("Copy ffclipper CLI command")
    copy_btn.setText("Copy ffclipper command")
    _apply_icon(copy_btn, "copy.svg")
    copy_btn.clicked.connect(window.controller.copy_cli)
    copy_btn.setMinimumHeight(32)
    button_layout.addWidget(copy_btn, 0)

    # Run button
    run_btn = QPushButton()
    run_btn.setToolTip("Run conversion")
    run_btn.setText("Run")
    _apply_icon(run_btn, "run.svg")
    run_btn.clicked.connect(window.controller.run)
    run_btn.setMinimumHeight(32)
    run_btn.setMinimumWidth(200)
    button_layout.addWidget(run_btn, 1)
    window.run_btn = run_btn

    window.layout.addLayout(button_layout)

    window.status_text = QTextEdit()
    window.status_text.setMaximumHeight(150)
    window.status_text.setReadOnly(True)
    window.layout.addWidget(window.status_text)

    window.progress_bar = QProgressBar()
    window.progress_bar.setVisible(False)
    window.layout.addWidget(window.progress_bar)


__all__ = ["build_ui"]
