from __future__ import annotations

import re
from typing import Any

"""Вспомогательные функции для стабильных идентификаторов задач.
    index — номер строки в Google Таблицах, используемый для синхронизации с таблицей.
    trip_number — внутренний номер задачи, используемый приложением и API."""


def to_int_or_none(value: Any) -> int | None:
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
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("google_sheet_row")) or to_int_or_none(row.get("index"))


def trip_number(row: dict[str, Any] | None) -> int | None:
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("trip_number"))


def vehicle_monitoring_id(row: dict[str, Any] | None) -> int | None:
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("vehicle_monitoring_id")) or to_int_or_none(row.get("id"))


def row_identity_for_gui(row: dict[str, Any] | None) -> int | None:
    return google_sheet_row(row) or trip_number(row)
