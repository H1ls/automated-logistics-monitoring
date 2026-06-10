from __future__ import annotations

import re
from typing import Any


"""
Единые правила чтения идентификаторов рейса из legacy-dict.

Пока GUI и часть сервисов работают со старым ключом "index". Сейчас он означает
строку Google Sheets. Внутренний номер рейса хранится отдельно: "trip_number".
Этот модуль нужен, чтобы не смешивать эти смыслы в коде.
"""


def to_int_or_none(value: Any) -> int | None:
    """Безопасно приводит значение к int, если это целое число."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    return None


def google_sheet_row(row: dict[str, Any] | None) -> int | None:
    """Возвращает номер строки Google Sheets из явного поля или legacy index."""
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("google_sheet_row")) or to_int_or_none(row.get("index"))


def trip_number(row: dict[str, Any] | None) -> int | None:
    """Возвращает внутренний номер рейса из trip_number или временного task_index alias."""
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("trip_number")) or to_int_or_none(row.get("task_index"))


def row_identity_for_gui(row: dict[str, Any] | None) -> int | None:
    """Ключ строки для GUI: сначала строка Google, иначе внутренний номер рейса."""
    return google_sheet_row(row) or trip_number(row)
