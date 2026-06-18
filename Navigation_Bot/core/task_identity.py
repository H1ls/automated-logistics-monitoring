from __future__ import annotations

import re
from typing import Any

"""Helpers for stable task identifiers.

``index`` is the Google Sheets row number kept for sheet sync.
``trip_number`` is the internal task number used by the application and API.
"""


def to_int_or_none(value: Any) -> int | None:
    """Return an int only when the value is a clean integer."""
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
    """Return the Google Sheets row number."""
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("google_sheet_row")) or to_int_or_none(row.get("index"))


def trip_number(row: dict[str, Any] | None) -> int | None:
    """Return the internal task number."""
    if not isinstance(row, dict):
        return None
    return to_int_or_none(row.get("trip_number"))


def row_identity_for_gui(row: dict[str, Any] | None) -> int | None:
    """Return the GUI row identity: Google row first, otherwise trip number."""
    return google_sheet_row(row) or trip_number(row)
