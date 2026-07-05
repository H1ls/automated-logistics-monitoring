from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QApplication
from Navigation_Bot.gui.debug import qt_debug_logger


class LoadingOverlayController:
    """
    Контроллер компактного loading overlay для главного окна.
    """

    def __init__(self, parent):
        self.parent = parent
        ui = getattr(parent, "ui", None)
        existing_overlay = getattr(ui, "loading_overlay", None) if ui is not None else None

        self._uses_page_overlay = existing_overlay is not None
        if self._uses_page_overlay:
            self.overlay = existing_overlay
            self.overlay.setObjectName("main_loading_overlay")
            self.label = getattr(ui, "loading_label", None)
            self.detail = None
            self.spinner = None
        else:
            self.overlay = QFrame(parent, Qt.WindowType.Widget)
            self.overlay.setObjectName("main_loading_overlay")
            self.overlay.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint)
            self.overlay.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, False)
            self.overlay.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
            self.overlay.setStyleSheet("QFrame { "
                                       "background-color: rgba(30, 30, 30, 240); "
                                       "border: 2px solid #bcbcbc; "
                                       "border-radius: 10px; "
                                       "}")

            self.overlay.setFrameShape(QFrame.Shape.StyledPanel)
            self.overlay.setFixedSize(350, 180)

            layout = QVBoxLayout(self.overlay)
            layout.setContentsMargins(20, 15, 20, 15)
            layout.setSpacing(10)

            self.spinner = QLabel("⠋")
            self.spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spinner_font = QFont()
            spinner_font.setPointSize(28)
            self.spinner.setFont(spinner_font)
            self.spinner.setStyleSheet("color: #4CAF50;")
            self.spinner.setFixedHeight(40)

            self.label = QLabel("Загрузка…")
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label_font = QFont()
            label_font.setPointSize(11)
            label_font.setBold(True)
            self.label.setFont(label_font)
            self.label.setStyleSheet("color: #ffffff;")
            self.label.setFixedHeight(20)

            self.detail = QLabel("Пожалуйста, подождите…")
            self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            detail_font = QFont()
            detail_font.setPointSize(8)
            self.detail.setFont(detail_font)
            self.detail.setStyleSheet("color: #aaaaaa;")
            self.detail.setFixedHeight(16)
            self.detail.setWordWrap(True)

            layout.addWidget(self.spinner)
            layout.addWidget(self.label)
            layout.addWidget(self.detail)

        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._frame_index = 0

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(80)

        self._delay_timer = QTimer(parent)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._show_pending)
        self._pending_text = "Загрузка…"
        self._pending_detail = "Пожалуйста, подождите…"
        self._generation = 0
        self._pending_generation = 0
        self._last_show_started_at = 0.0

        self.overlay.hide()

    def _tick(self):
        if self.spinner is None:
            return
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.spinner.setText(self._frames[self._frame_index])

    def reposition(self):
        if self._uses_page_overlay:
            parent_widget = self.overlay.parentWidget()
            if parent_widget is not None:
                self.overlay.setGeometry(parent_widget.rect())
            return

        x = (self.parent.width() - self.overlay.width()) // 2
        y = (self.parent.height() - self.overlay.height()) // 2
        self.overlay.move(x, y)

    def show(self, text="Загрузка…", detail="Пожалуйста, подождите…"):
        self._generation += 1
        self._delay_timer.stop()
        if self.label is not None:
            self.label.setText(text)
        if self.detail is not None:
            self.detail.setText(detail)
        if hasattr(self.parent, "update_startup_status"):
            self.parent.update_startup_status(text, detail)
        if getattr(self.parent, "startup_splash", None) is not None:
            qt_debug_logger.log(self.parent, "UI loading", f"show skipped because startup_splash is active text={text!r}")
            return
        self.reposition()
        self.overlay.show()
        self.overlay.raise_()
        self._last_show_started_at = time.perf_counter()
        top_left = self.overlay.mapToGlobal(QPoint(0, 0))
        parent_geo = self.parent.geometry()
        qt_debug_logger.log(self.parent, "UI loading",
                            f"show generation={self._generation} text={text!r} detail={detail!r} "
                            f"visible={self.overlay.isVisible()} pos=({self.overlay.x()},{self.overlay.y()}) "
                            f"global=({top_left.x()},{top_left.y()}) "
                            f"size=({self.overlay.width()}x{self.overlay.height()}) "
                            f"usesPageOverlay={self._uses_page_overlay} "
                            f"isWindow={self.overlay.isWindow()} flags={int(self.overlay.windowFlags())} "
                            f"parentGeometry=({parent_geo.x()},{parent_geo.y()},{parent_geo.width()}x{parent_geo.height()})")
        qt_debug_logger.dump_top_level_widgets(self.parent, "during loading.show")
        qt_debug_logger.dump_top_level_widgets_later(self.parent, "during loading.show +50ms", 50)

        if not self._timer.isActive():
            self._timer.start()

        self.overlay.update()

    def show_delayed(self,text="Загрузка…",detail="Пожалуйста, подождите…",delay_ms: int = 250) -> None:
        """Показывать наложение только тогда, когда операция занимает достаточно времени, чтобы это стало заметно"""
        self._generation += 1
        self._pending_generation = self._generation
        self._pending_text = text
        self._pending_detail = detail
        self._delay_timer.start(max(0, delay_ms))
        qt_debug_logger.log(self.parent, "UI loading",
                            f"show_delayed generation={self._pending_generation} delay_ms={delay_ms} "
                            f"text={text!r} visible={self.overlay.isVisible()}")

    def _show_pending(self) -> None:
        if self._pending_generation != self._generation:
            qt_debug_logger.log(self.parent, "UI loading",
                                f"skip stale delayed show pending_generation={self._pending_generation} "
                                f"current_generation={self._generation}")
            return
        qt_debug_logger.log(self.parent, "UI loading", f"delayed timer fired generation={self._pending_generation}")
        self.show(self._pending_text, self._pending_detail)

    def hide(self):
        self._generation += 1
        visible_before = self.overlay.isVisible()
        elapsed = time.perf_counter() - self._last_show_started_at if self._last_show_started_at else 0.0
        self._delay_timer.stop()
        self.overlay.hide()
        self._timer.stop()
        qt_debug_logger.log(self.parent, "UI loading",
                            f"hide generation={self._generation} visible_before={visible_before} "
                            f"shown_for={elapsed:.3f}s")
        self.overlay.update()

    @staticmethod
    def sync_paint():
        QApplication.processEvents()
