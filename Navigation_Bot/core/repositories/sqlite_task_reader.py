from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from Navigation_Bot.core.geo_coordinates import format_coordinate_pair

"""
SqliteTaskReader делает противоположное тому, что делает SqliteTaskWriter:
    - Берёт нормализованные таблицы из SQLite
    - Собирает их в старый "плоский" словарь (legacy-dict)
    - Отдаёт его GUI и старым сервисам с привычными ключами

Старый код продолжает работать без изменений.
"""


@dataclass(slots=True)
class SqliteTaskReader:
    """Отвечает только за SELECT-запросы и сборку legacy-представления рейса."""

    connection: sqlite3.Connection

    def load_active_rows(self, source_key: str = "") -> list[dict]:
        """Загружает активные рейсы текущего листа Google и возвращает legacy-dict."""
        rows = self.connection.execute(
            """
            SELECT
                t.*,
                v.plate_number,
                v.monitoring_id,
                c.name AS carrier_name,
                d.full_name AS driver_name,
                d.phone AS driver_phone
            FROM tasks t
            LEFT JOIN vehicles v ON v.id = t.vehicle_id
            LEFT JOIN carriers c ON c.id = t.carrier_id
            LEFT JOIN drivers d ON d.id = t.driver_id
            WHERE t.status NOT IN ('completed', 'archived', 'cancelled')
              AND (? = '' OR t.google_worksheet_title = ? OR t.google_worksheet_title IS NULL)
            ORDER BY COALESCE(t.google_sheet_row, t.trip_number), t.id
            """,
            (source_key, source_key),
        ).fetchall()
        return [self._task_db_row_to_legacy_dict(row) for row in rows]

    def _task_db_row_to_legacy_dict(self, row: sqlite3.Row) -> dict:
        """Собирает одну строку GUI из tasks + справочников + связанных историй."""
        task_id = int(row["id"])
        loads = self._route_points_to_legacy_blocks(task_id, "load", "Погрузка")
        unloads = self._route_points_to_legacy_blocks(task_id, "unload", "Выгрузка")
        processed = self._processed_flags(task_id)

        result = {
            # index оставлен для совместимости; явно хранит строку Google, если она есть.
            "index": row["google_sheet_row"],
            "google_sheet_row": row["google_sheet_row"],
            # trip_number - внутренний номер рейса. task_index оставлен временным alias.
            "trip_number": row["trip_number"],
            "task_index": row["trip_number"],
            "db_task_id": row["id"],
            "status": row["status"] or "",
            "ТС": row["plate_number"] or "",
            "Телефон": row["driver_phone"] or "",
            "ФИО": row["driver_name"] or "",
            "КА": row["carrier_name"] or "",
            "Погрузка": loads,
            "Выгрузка": unloads,
            "processed": processed,
            "raw_load": row["raw_load"] or "",
            "raw_unload": row["raw_unload"] or "",
        }

        if row["monitoring_id"] is not None:
            result["id"] = row["monitoring_id"]
        if row["highlight_until"]:
            result["highlight_until"] = row["highlight_until"]

        navigation = self._latest_navigation(task_id)
        if navigation:
            result.update(navigation)

        estimate = self._latest_route_estimate(task_id)
        if estimate:
            result["Маршрут"] = estimate

        return result

    def _route_points_to_legacy_blocks(self, task_id: int, point_type: str, prefix: str) -> list[dict]:
        """Преобразует route_points обратно в старый список блоков погрузки/выгрузки."""
        rows = self.connection.execute(
            """
            SELECT sequence, location, scheduled_time, comment, latitude, longitude
            FROM route_points
            WHERE task_id = ? AND point_type = ?
            ORDER BY sequence
            """,
            (task_id, point_type),
        ).fetchall()

        result = []
        for row in rows:
            seq = int(row["sequence"])
            date, time = self._split_datetime_text(row["scheduled_time"])
            if row["location"] or row["scheduled_time"]:
                block = {
                    f"{prefix} {seq}": row["location"] or "",
                    f"Дата {seq}": date,
                    f"Время {seq}": time,
                }
                coordinates = format_coordinate_pair(row["latitude"], row["longitude"])
                if coordinates:
                    block[f"Координаты {seq}"] = coordinates
                result.append(block)
            if row["comment"]:
                result.append({"Комментарий": row["comment"]})
        return result

    def _processed_flags(self, task_id: int) -> list[bool]:
        """Возвращает processed-флаги по выгрузкам в порядке sequence."""
        rows = self.connection.execute(
            """
            SELECT is_processed
            FROM route_points
            WHERE task_id = ? AND point_type = 'unload'
            ORDER BY sequence
            """,
            (task_id,),
        ).fetchall()
        return [bool(row["is_processed"]) for row in rows]

    def _latest_navigation(self, task_id: int) -> dict:
        """Подмешивает в строку последние навигационные данные по рейсу."""
        row = self.connection.execute(
            """
            SELECT geo_text, geo_zona, coordinates, speed_kmh,
                   gps_fix_text, gps_fix_age_seconds, has_fresh_coordinates
            FROM vehicle_navigation_history
            WHERE task_id = ?
            ORDER BY collected_at DESC, id DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return {}

        result = {
            "гео": row["geo_text"] or "",
            "geo_zona": row["geo_zona"] or "",
            "коор": row["coordinates"] or "",
            "_новые_координаты": bool(row["has_fresh_coordinates"]),
        }
        if row["speed_kmh"] is not None:
            result["скорость"] = row["speed_kmh"]
        if row["gps_fix_text"] or row["gps_fix_age_seconds"] is not None:
            result["gps_fix_age"] = {
                "text": row["gps_fix_text"] or "",
                "age_second": row["gps_fix_age_seconds"],
            }
        return result

    def _latest_route_estimate(self, task_id: int) -> dict:
        """Подмешивает последний расчет маршрута по рейсу."""
        row = self.connection.execute(
            """
            SELECT distance_km, duration_minutes, arrival_time, on_time,
                   buffer_minutes, time_buffer_text
            FROM route_estimates
            WHERE task_id = ?
            ORDER BY calculated_at DESC, id DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return {}
        return {
            "расстояние": f"{row['distance_km']} км",
            "длительность": f"{row['duration_minutes']} мин",
            "время прибытия": row["arrival_time"] or "",
            "успеет": bool(row["on_time"]),
            "time_buffer": row["time_buffer_text"] or "",
            "buffer_minutes": row["buffer_minutes"],
        }

    @staticmethod
    def _split_datetime_text(value: Any) -> tuple[str, str]:
        """Разделяет сохраненное scheduled_time на старые поля Дата/Время."""
        text = str(value or "").strip()
        if not text:
            return "", ""
        parts = text.split()
        if len(parts) >= 2:
            return parts[0], parts[1]
        if ":" in text:
            return "", text
        return text, ""
