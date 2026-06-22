from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QApplication


class LoadingOverlayController:
    """
    Контроллер компактного loading overlay для главного окна.
    """

    def __init__(self, parent):
        self.parent = parent

        self.overlay = QFrame(parent)
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

        self.overlay.hide()

    def _tick(self):
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.spinner.setText(self._frames[self._frame_index])

    def reposition(self):
        x = (self.parent.width() - self.overlay.width()) // 2
        y = (self.parent.height() - self.overlay.height()) // 2
        self.overlay.move(x, y)

    def show(self, text="Загрузка…", detail="Пожалуйста, подождите…"):
        self._delay_timer.stop()
        self.label.setText(text)
        self.detail.setText(detail)
        self.reposition()
        self.overlay.show()
        self.overlay.raise_()

        if not self._timer.isActive():
            self._timer.start()

        self.sync_paint()

    def show_delayed(
        self,
        text="Загрузка…",
        detail="Пожалуйста, подождите…",
        delay_ms: int = 250,
    ) -> None:
        """Show the overlay only when an operation takes long enough to notice."""
        self._pending_text = text
        self._pending_detail = detail
        self._delay_timer.start(max(0, delay_ms))

    def _show_pending(self) -> None:
        self.show(self._pending_text, self._pending_detail)

    def hide(self):
        self._delay_timer.stop()
        self.overlay.hide()
        self._timer.stop()
        self.sync_paint()

    @staticmethod
    def sync_paint():
        QApplication.processEvents()
