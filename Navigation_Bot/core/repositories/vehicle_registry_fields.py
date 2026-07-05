from __future__ import annotations

import re
from typing import Any

ID_FIELD = "ИДОбъекта в центре мониторинга"
NAME_FIELD = "Наименование"
TS_FIELD = "ТС"
CENTER_FIELD = "Центр мониторинга"
DB_ID_FIELD = "_vehicle_db_id"
DEFAULT_MONITORING_CENTER = "Виалон"


def compact_vehicle_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def base_vehicle_key(value: Any) -> str:
    key = compact_vehicle_key(value)
    match = re.fullmatch(r"([^\W\d_]\d{3}[^\W\d_]{2})(\d{2,3})", key, re.UNICODE)
    return match.group(1) if match else key


def vehicle_lookup_keys(*values: Any) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        for key in (compact_vehicle_key(value), base_vehicle_key(value)):
            if key and key not in seen:
                keys.append(key)
                seen.add(key)
    return keys


def plate_from_monitoring_name(name: Any) -> str:
    value = str(name or "").strip()
    if len(value) >= 7:
        return f"{value[0]} {value[1:4]} {value[4:6]} {value[6:]}"
    return value
