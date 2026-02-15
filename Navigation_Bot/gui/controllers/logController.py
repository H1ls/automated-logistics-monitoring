from __future__ import annotations

from PyQt6.QtGui import QTextCursor


class LogController:
    def __init__(self, log_box, enabled_getter=None):
        """
        log_box: QTextEdit
        enabled_getter: callable -> bool (например lambda: gui._log_enabled)
        """
        self.log_box = log_box
        self.enabled_getter = enabled_getter or (lambda: True)

    def clear(self):
        self.log_box.clear()

    def log(self, message: str):
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

        # автоскролл вниз
        cursor = self.log_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_box.setTextCursor(cursor)
