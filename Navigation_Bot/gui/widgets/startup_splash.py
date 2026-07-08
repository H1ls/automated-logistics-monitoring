from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen


class StartupSplash:
    AUTO_PROGRESS_STEP = 5

    def __init__(self):
        self._progress = 0
        self._last_message = ""
        self._completed = False
        self._subtitle = "Подготовка приложения"
        self._bar_x = 36
        self._bar_y = 198
        self._bar_width = 448
        self._bar_height = 6
        pixmap = self._render_pixmap()

        self.splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        self.splash.setWindowFlag(Qt.WindowType.FramelessWindowHint)

    def _render_pixmap(self) -> QPixmap:
        pixmap = QPixmap(520, 260)
        pixmap.fill(QColor("#20232a"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        title_font = QFont()
        title_font.setPointSize(22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(34, 58, "Navigation Manager")

        subtitle_font = QFont()
        subtitle_font.setPointSize(10)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#b8c0cc"))
        painter.drawText(36, 88, self._subtitle)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#323740"))
        painter.drawRoundedRect(self._bar_x, self._bar_y, self._bar_width, self._bar_height, 3, 3)

        fill_width = int(self._bar_width * max(0, min(100, self._progress)) / 100)
        painter.setBrush(QColor("#4caf50"))
        if fill_width > 0:
            painter.drawRoundedRect(self._bar_x, self._bar_y, fill_width, self._bar_height, 3, 3)
        painter.end()

        return pixmap

    def _set_progress(self, value: int) -> None:
        self._progress = max(self._progress, max(0, min(100, value)))
        if self._progress >= 100:
            self._completed = True

    @staticmethod
    def _normalize_message(message: str) -> str:
        return message.replace("…", "...").strip()

    def _advance_progress(self, message: str) -> None:
        normalized_message = self._normalize_message(message)
        if normalized_message == self._last_message:
            return
        self._last_message = normalized_message

        if normalized_message.startswith("Готово"):
            self._set_progress(100)
            return

        if self._completed:
            return

        self._set_progress(min(96, self._progress + self.AUTO_PROGRESS_STEP))

    def show(self, text: str, detail: str = "", progress: int | None = None) -> None:
        if self.splash is None:
            return
        self.splash.show()
        self.update(text, detail, progress=progress)

    def update(self, text: str, detail: str = "", progress: int | None = None) -> None:
        if self.splash is None:
            return
        message = text if not detail else f"{text}\n{detail}"
        if progress is None:
            self._advance_progress(message)
        else:
            self._set_progress(progress)
            self._last_message = self._normalize_message(message)
        self.splash.setPixmap(self._render_pixmap())
        self.splash.showMessage(message,
                                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                                QColor("#ffffff")
                                )
        QApplication.processEvents()

    def finish(self, widget=None) -> None:
        if self.splash is None:
            return
        if widget is not None:
            self.splash.finish(widget)
        else:
            self.splash.close()
        self.splash.hide()
        self.splash.deleteLater()
        self.splash = None
        QApplication.processEvents()
