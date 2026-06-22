from __future__ import annotations

from datetime import datetime, timedelta

from Navigation_Bot.core.domain.task_identity import row_identity_for_gui


class TaskProcessingSelector:
    @staticmethod
    def get_processible_rows(data: list) -> list[tuple[int, int | None]]:
        result: list[tuple[int, int | None]] = []

        for row_idx, row in enumerate(data):
            if not isinstance(row, dict):
                continue
            if not TaskProcessingSelector._has_vehicle_identity(row):
                continue
            if TaskProcessingSelector.is_future_load(row):
                continue

            result.append((row_idx, row_identity_for_gui(row)))

        return result

    @staticmethod
    def is_future_load(row: dict) -> bool:
        date_str, time_str = TaskProcessingSelector._first_load_datetime_parts(row)
        if not date_str or not time_str:
            return False

        try:
            if time_str and time_str.count(":") == 1:
                time_str += ":00"
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            return dt > datetime.now() + timedelta(hours=3)
        except Exception:
            return False

    @staticmethod
    def _has_vehicle_identity(row: dict) -> bool:
        monitoring_id = row.get("vehicle_monitoring_id") or row.get("id")
        plate_or_name = row.get("vehicle_plate") or row.get("ТС")
        return bool(monitoring_id and plate_or_name)

    @staticmethod
    def _first_load_datetime_parts(row: dict) -> tuple[str, str]:
        loads = row.get("loads")
        if isinstance(loads, list) and loads:
            first = loads[0]
            if isinstance(first, dict):
                return str(first.get("date") or ""), str(first.get("time") or "")

        legacy_loads = row.get("Погрузка", [])
        if isinstance(legacy_loads, list) and legacy_loads and isinstance(legacy_loads[0], dict):
            return str(legacy_loads[0].get("Дата 1") or ""), str(legacy_loads[0].get("Время 1") or "")

        return "", ""
