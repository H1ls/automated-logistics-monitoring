from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTextCursor


class LogController(QObject):
    message = pyqtSignal(str)
    clear_requested = pyqtSignal()

    def __init__(self, log_box, enabled_getter=None):
        super().__init__()
        self.log_box = log_box
        self.enabled_getter = enabled_getter or (lambda: True)

        # все UI-операции — только через сигналы (GUI-thread)
        self.message.connect(self._append_log)
        self.clear_requested.connect(self._clear_log)

    def clear(self):
        # можно вызывать из любого потока
        self.clear_requested.emit()

    def log(self, message: str):
        # можно вызывать из любого потока
        self.message.emit(str(message))

    def _clear_log(self):
        self.log_box.clear()

    def _append_log(self, message: str):
        if not self.enabled_getter():
            return

        text = str(message)
        lower = text.lower()
        color = None

        if text.startswith("❌") or "ошибка" in lower or "error" in lower:
            color = "red"
        elif text.startswith("✅") or "успеш" in lower or "успех" in lower:
            color = "green"
        elif text.startswith("⚠") or "предупр" in lower or "warning" in lower:
            color = "#c08000"

        if color:
            self.log_box.append(f'<span style="color:{color};">{text}</span>')
        else:
            self.log_box.append(text)

        cursor = self.log_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_box.setTextCursor(cursor)
