from __future__ import annotations

from datetime import datetime
from html import escape

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTextCursor


class LogController(QObject):
    message = pyqtSignal(str)
    clear_requested = pyqtSignal()

    def __init__(self, log_box, enabled_getter=None, max_blocks: int = 1500, with_timestamp: bool = True):
        super().__init__()
        self.log_box = log_box
        self.enabled_getter = enabled_getter or (lambda: True)
        self.max_blocks = max_blocks
        self.with_timestamp = with_timestamp

        # все UI-операции — только через сигналы (GUI-thread)
        self.message.connect(self._append_log)
        self.clear_requested.connect(self._clear_log)

    # ---------------- public API ----------------

    def clear(self):
        """Можно вызывать из любого потока."""
        self.clear_requested.emit()

    def log(self, message: str):
        """Можно вызывать из любого потока."""
        self.message.emit(str(message))

    def log_info(self, message: str):
        self.log(f"ℹ️ {message}")

    def log_success(self, message: str):
        self.log(f"✅ {message}")

    def log_warning(self, message: str):
        self.log(f"⚠️ {message}")

    def log_error(self, message: str):
        self.log(f"❌ {message}")

    # ---------------- internal ----------------

    def _clear_log(self):
        self.log_box.clear()

    def _append_log(self, message: str):
        if not self.enabled_getter():
            return

        text = str(message)
        level = self._detect_level(text)
        html = self._format_html(text, level)

        should_autoscroll = self._is_near_bottom()
        self.log_box.append(html)

        self._trim_blocks()

        if should_autoscroll:
            self._scroll_to_end()

    def _detect_level(self, text: str) -> str:
        lower = text.lower()

        if (
            text.startswith("❌")
            or text.startswith("⛔")
            or "ошибка" in lower
            or "error" in lower
            or "traceback" in lower
            or "exception" in lower
        ):
            return "error"

        if (
            text.startswith("⚠")
            or text.startswith("⌛")
            or text.startswith("ℹ️")
            or text.startswith("🔁")
            or "предупр" in lower
            or "warning" in lower
        ):
            return "warning"

        if (
            text.startswith("✅")
            or text.startswith("📡")
            or text.startswith("🗺️")
            or text.startswith("🔄")
            or "успеш" in lower
            or "успех" in lower
        ):
            return "success"
        if (
            text.startswith("🌎")
        ):
            return "upload"
        return "default"

    def _format_html(self, text: str, level: str) -> str:
        color = self._level_color(level)
        safe_text = escape(text)

        if self.with_timestamp:
            ts = datetime.now().strftime("%H:%M:%S")
            safe_text = f"[{ts}] {safe_text}"

        if color:
            return f'<span style="color:{color};">{safe_text}</span>'
        return safe_text

    @staticmethod
    def _level_color(level: str) -> str | None:
        colors = {
            "error": "red",
            "success": "green",
            "warning": "#c08000",
            "upload" : "blue",
            "default": None,
        }
        return colors.get(level)

    def _scroll_to_end(self):
        cursor = self.log_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_box.setTextCursor(cursor)
        self.log_box.ensureCursorVisible()

    def _is_near_bottom(self, threshold: int = 20) -> bool:
        sb = self.log_box.verticalScrollBar()
        return (sb.maximum() - sb.value()) <= threshold

    def _trim_blocks(self):
        doc = self.log_box.document()
        overflow = doc.blockCount() - self.max_blocks
        if overflow <= 0:
            return

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        for _ in range(overflow):
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()