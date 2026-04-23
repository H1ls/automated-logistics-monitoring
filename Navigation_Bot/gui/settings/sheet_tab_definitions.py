"""
Статические вкладки (данные не из Google Sheets).
Динамические вкладки строятся в SheetTabsController из списка листов gspread.
"""

from __future__ import annotations

# Ключи в ui_settings["tabs"]["active_key"] / ["hidden_keys"]
KEY_LOCAL_PINCODES = "local:pincodes"
KEY_LOCAL_LOGISTX = "local:logistx"


def default_local_tabs() -> list[dict]:
    """Порядок и заголовки локальных вкладок (Пин-коды, LogistX)."""
    return [{"kind": "local", "key": KEY_LOCAL_PINCODES, "title": "Пин коды"},
            {"kind": "local", "key": KEY_LOCAL_LOGISTX, "title": "LogistX"},]
