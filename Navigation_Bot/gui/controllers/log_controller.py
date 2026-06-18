from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from html import escape

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTextCursor


class LogAudience(str, Enum):
    USER = "user"
    USER_PLUS = "user+"
    ADMIN = "admin"


class LogSeverity(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class LogRecord:
    message: str
    severity: LogSeverity = LogSeverity.INFO
    audience: LogAudience = LogAudience.USER


class LogController(QObject):
    """
    Thread-safe QTextEdit logger with explicit severity and audience filtering.

    Compatibility:
    - log("text") means info/user.
    - log("text", audience="admin", severity="error") is supported.
    """

    _AUDIENCE_RANK = {LogAudience.USER: 0,
                      LogAudience.USER_PLUS: 1,
                      LogAudience.ADMIN: 2}

    _SEVERITY_COLORS = {LogSeverity.INFO: None,
                        LogSeverity.SUCCESS: "green",
                        LogSeverity.WARNING: "#c08000",
                        LogSeverity.ERROR: "red"}

    message = pyqtSignal(object)
    clear_requested = pyqtSignal()

    def __init__(self,
                 log_box,
                 enabled_getter=None,
                 max_blocks: int = 1500,
                 with_timestamp: bool = True,
                 audience: str | LogAudience = LogAudience.USER,
                 with_severity_label: bool = True):

        super().__init__()
        self.log_box = log_box
        self.enabled_getter = enabled_getter or (lambda: True)
        self.max_blocks = max_blocks
        self.with_timestamp = with_timestamp
        self.with_severity_label = with_severity_label
        self.audience = self._normalize_audience(audience)

        self.message.connect(self._append_record)
        self.clear_requested.connect(self._clear_log)

    # --- public API
    def clear(self):
        self.clear_requested.emit()

    def set_audience(self, audience: str | LogAudience):
        self.audience = self._normalize_audience(audience)

    def get_audience(self) -> str:
        return self.audience.value

    def log(self, message: str, audience: str | LogAudience = LogAudience.USER,
            severity: str | LogSeverity = LogSeverity.INFO):
        """self.log(f"❗️Ошибка",severity="error",audience="user+", )"""
        self.emit_record(message=message, severity=severity, audience=audience)

    def emit_record(self, message: str, severity: str | LogSeverity = LogSeverity.INFO,
                    audience: str | LogAudience = LogAudience.USER):
        record = LogRecord(message=str(message),
                           severity=self._normalize_severity(severity),
                           audience=self._normalize_audience(audience))
        self.message.emit(record)

    def info(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.emit_record(message, severity=LogSeverity.INFO, audience=audience)

    def success(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.emit_record(message, severity=LogSeverity.SUCCESS, audience=audience)

    def warning(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.emit_record(message, severity=LogSeverity.WARNING, audience=audience)

    def error(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.emit_record(message, severity=LogSeverity.ERROR, audience=audience)

    # Backward-compatible method names.
    def log_user(self, message: str):
        self.info(message, audience=LogAudience.USER)

    def log_user_plus(self, message: str):
        self.info(message, audience=LogAudience.USER_PLUS)

    def log_admin(self, message: str):
        self.info(message, audience=LogAudience.ADMIN)

    def log_info(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.info(message, audience=audience)

    def log_success(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.success(message, audience=audience)

    def log_warning(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.warning(message, audience=audience)

    def log_error(self, message: str, audience: str | LogAudience = LogAudience.USER):
        self.error(message, audience=audience)

    # ---
    def _clear_log(self):
        self.log_box.clear()

    def _append_record(self, record: LogRecord):
        if not self.enabled_getter():
            return
        if not self._should_show(record.audience):
            return

        should_autoscroll = self._is_near_bottom()
        self.log_box.append(self._format_html(record))
        self._trim_blocks()

        if should_autoscroll:
            self._scroll_to_end()

    def _should_show(self, audience: LogAudience) -> bool:
        return self._AUDIENCE_RANK[audience] <= self._AUDIENCE_RANK[self.audience]

    def _format_html(self, record: LogRecord) -> str:
        safe_parts = []

        if self.with_timestamp:
            safe_parts.append(f"[{datetime.now():%H:%M:%S}]")
        if self.with_severity_label:
            safe_parts.append(f"[{record.severity.value.upper()}]")

        safe_parts.append(escape(record.message, quote=False))
        safe_text = " ".join(safe_parts)

        color = self._SEVERITY_COLORS.get(record.severity)
        if not color:
            return safe_text

        return f'<span style="color:{color};">{safe_text}</span>'

    @classmethod
    def _normalize_audience(cls, audience: str | LogAudience | None) -> LogAudience:
        if isinstance(audience, LogAudience):
            return audience

        value = str(audience or LogAudience.USER.value).strip().lower()
        aliases = {"user": LogAudience.USER,
                   "user+": LogAudience.USER_PLUS,
                   "user_plus": LogAudience.USER_PLUS,
                   "plus": LogAudience.USER_PLUS,
                   "admin": LogAudience.ADMIN}

        return aliases.get(value, LogAudience.USER)

    @classmethod
    def _normalize_severity(cls, severity: str | LogSeverity | None) -> LogSeverity:
        if isinstance(severity, LogSeverity):
            return severity

        value = str(severity or LogSeverity.INFO.value).strip().lower()
        aliases = {"info": LogSeverity.INFO,
                   "success": LogSeverity.SUCCESS,
                   "ok": LogSeverity.SUCCESS,
                   "warning": LogSeverity.WARNING,
                   "warn": LogSeverity.WARNING,
                   "error": LogSeverity.ERROR,
                   "err": LogSeverity.ERROR}

        return aliases.get(value, LogSeverity.INFO)

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
