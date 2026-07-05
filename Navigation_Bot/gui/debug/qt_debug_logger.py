from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QSplashScreen, QWidget

ENABLED = False


def log(gui, scope: str, message: str) -> None:
    if not ENABLED:
        return
    logger = getattr(gui, "log", None)
    if not logger:
        return
    text = f"🧭 {scope}: {message}"
    try:
        logger(text, audience="admin")
    except TypeError:
        logger(text)


def dump_top_level_widgets(gui, label: str = "") -> None:
    if not ENABLED:
        return

    widgets = QApplication.topLevelWidgets()
    log(gui, "Qt top-level", f"widgets {label}: count={len(widgets)}")
    for idx, widget in enumerate(widgets):
        geo = widget.geometry()
        parent = widget.parent()
        log(
            gui,
            "Qt top-level",
            f"#{idx}: class={type(widget).__name__} "
            f"title={widget.windowTitle()!r} "
            f"visible={widget.isVisible()} "
            f"active={widget.isActiveWindow()} "
            f"minimized={widget.isMinimized()} "
            f"flags={int(widget.windowFlags())} "
            f"geometry=({geo.x()},{geo.y()},{geo.width()}x{geo.height()}) "
            f"objectName={widget.objectName()!r} "
            f"parent={type(parent).__name__ if parent else None}",
        )


def dump_top_level_widgets_later(gui, label: str, delay_ms: int) -> None:
    if not ENABLED:
        return
    QTimer.singleShot(delay_ms, lambda: dump_top_level_widgets(gui, label))


class QtWidgetLifecycleLogger(QObject):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui

    def install(self) -> None:
        if not ENABLED:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def uninstall(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, watched, event):
        if ENABLED and event.type() in {
            QEvent.Type.Show,
            QEvent.Type.Hide,
            QEvent.Type.ShowToParent,
            QEvent.Type.HideToParent,
            QEvent.Type.WinIdChange,
        }:
            self._log_widget_lifecycle_event(watched, event)
        return super().eventFilter(watched, event)

    def _log_widget_lifecycle_event(self, widget, event) -> None:
        if not isinstance(widget, QWidget):
            return

        object_name = widget.objectName() or ""
        should_log = (
                widget.isWindow()
                or object_name in {"main_loading_overlay", "sheet_filter_menu", "sheet_filter_button"}
                or isinstance(widget, (QMenu, QDialog, QSplashScreen)))
        if not should_log:
            return

        geo = widget.geometry()
        try:
            global_pos = widget.mapToGlobal(widget.rect().topLeft())
            global_text = f"global=({global_pos.x()},{global_pos.y()})"
        except Exception:
            global_text = "global=<n/a>"

        parent = widget.parent()
        log(self.gui,
            "Qt event",
            f"{event.type().name}: class={type(widget).__name__} "
            f"title={widget.windowTitle()!r} "
            f"visible={widget.isVisible()} "
            f"isWindow={widget.isWindow()} "
            f"flags={int(widget.windowFlags())} "
            f"geometry=({geo.x()},{geo.y()},{geo.width()}x{geo.height()}) "
            f"{global_text} "
            f"objectName={object_name!r} "
            f"parent={type(parent).__name__ if parent else None}")
