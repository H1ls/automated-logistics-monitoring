from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from Navigation_Bot.core.domain.geo_coordinates import format_coordinate_pair


@dataclass(slots=True)
class PostgresTaskReader:
    connection: Any

    def load_active_rows(self, source_key: str = "", *, include_null_source: bool = True) -> list[dict]:
        source_filter, source_params = self._source_filter_sql(source_key, include_null_source=include_null_source)
        rows = self.connection.execute(
            f"""
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
              AND {source_filter}
            ORDER BY COALESCE(t.google_sheet_row, t.trip_number), t.id
            """,
            source_params,
        ).fetchall()
        return self._rows_to_gui_dicts(rows)

    def load_active_rows_page(self,
                              source_key: str = "",
                              *,
                              include_null_source: bool = True,
                              limit: int = 100,
                              offset: int = 0,
                              updated_since: str | None = None,
                              include_completed: bool = False,
                              date_from: str | None = None,
                              date_to: str | None = None) -> tuple[list[dict], int]:

        source_filter, source_params = self._source_filter_sql(source_key, include_null_source=include_null_source)
        conditions = [source_filter]
        if not updated_since and not include_completed:
            conditions.append("t.status NOT IN ('completed', 'archived', 'cancelled')")
        params: list[Any] = list(source_params)
        if updated_since:
            conditions.append("t.updated_at > %s::timestamptz")
            params.append(updated_since)
        task_date_sql = self._task_date_sql()
        if date_from:
            conditions.append(f"{task_date_sql} >= %s::date")
            params.append(date_from)
        if date_to:
            conditions.append(f"{task_date_sql} <= %s::date")
            params.append(date_to)

        where_sql = " AND ".join(conditions)
        total_row = self.connection.execute(
            f"SELECT COUNT(*) AS count FROM tasks t WHERE {where_sql}",
            tuple(params),
        ).fetchone()
        total = int(total_row["count"] or 0)

        rows = self.connection.execute(
            f"""
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
            WHERE {where_sql}
            ORDER BY t.updated_at, t.id
            LIMIT %s OFFSET %s
            """,
            tuple(params + [max(1, int(limit)), max(0, int(offset))]),
        ).fetchall()
        return self._rows_to_gui_dicts(rows), total

    @staticmethod
    def _task_date_sql() -> str:
        value_sql = "COALESCE(NULLIF(t.planned_start_at, ''), NULLIF(t.planned_end_at, ''), NULLIF(t.completed_at, ''))"
        return f"""
        (
            CASE
                WHEN {value_sql} ~ '^\\d{{2}}\\.\\d{{2}}\\.\\d{{4}}'
                    THEN to_date(substr({value_sql}, 1, 10), 'DD.MM.YYYY')
                WHEN {value_sql} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
                    THEN substr({value_sql}, 1, 10)::date
                ELSE NULL
            END
        )
        """

    @staticmethod
    def _source_filter_sql(source_key: str, *, include_null_source: bool) -> tuple[str, tuple[Any, ...]]:
        if not source_key:
            return "%s = ''", (source_key,)
        if include_null_source:
            return "(%s = '' OR t.google_worksheet_title = %s OR t.google_worksheet_title IS NULL)", (source_key,
                                                                                                      source_key)
        return "t.google_worksheet_title = %s", (source_key,)

    def _rows_to_gui_dicts(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []

        task_ids = [int(row["id"]) for row in rows]
        route_points = self._load_route_points(task_ids)
        latest_navigation = self._load_latest_navigation(task_ids)
        latest_estimates = self._load_latest_route_estimates(task_ids)

        return [self._task_row_to_gui_dict(row,
                                           route_points=route_points,
                                           latest_navigation=latest_navigation,
                                           latest_estimates=latest_estimates )
                for row in rows ]

    def _load_route_points(self, task_ids: list[int]) -> dict[tuple[int, str], list[dict]]:
        rows = self.connection.execute(
            """
            SELECT task_id, sequence, point_type, location, scheduled_time,
                   comment, latitude, longitude, is_processed
            FROM route_points
            WHERE task_id = ANY(%s)
            ORDER BY task_id, point_type, sequence
            """,
            (task_ids,),
        ).fetchall()

        grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
        for row in rows:
            grouped[(int(row["task_id"]), str(row["point_type"] or ""))].append(row)
        return grouped

    def _load_latest_navigation(self, task_ids: list[int]) -> dict[int, dict]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (task_id)
                   task_id, geo_text, geo_zona, coordinates, speed_kmh,
                   gps_fix_text, gps_fix_age_seconds, has_fresh_coordinates
            FROM vehicle_navigation_history
            WHERE task_id = ANY(%s)
            ORDER BY task_id, collected_at DESC, id DESC
            """,
            (task_ids,),
        ).fetchall()
        return {int(row["task_id"]): row for row in rows}

    def _load_latest_route_estimates(self, task_ids: list[int]) -> dict[int, dict]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (task_id)
                   task_id, distance_km, duration_minutes, arrival_time,
                   on_time, buffer_minutes, time_buffer_text
            FROM route_estimates
            WHERE task_id = ANY(%s)
            ORDER BY task_id, calculated_at DESC, id DESC
            """,
            (task_ids,),
        ).fetchall()
        return {int(row["task_id"]): row for row in rows}

    def _task_row_to_gui_dict(
            self,
            row: dict[str, Any],
            *,
            route_points: dict[tuple[int, str], list[dict]],
            latest_navigation: dict[int, dict],
            latest_estimates: dict[int, dict],
    ) -> dict[str, Any]:
        task_id = int(row["id"])
        result: dict[str, Any] = {
            "vehicle_plate": row["plate_number"] or "",
            "vehicle_monitoring_id": row["monitoring_id"],
            "driver_name": row["driver_name"] or "",
            "driver_phone": row["driver_phone"] or "",
            "carrier_name": row["carrier_name"] or "",
            "index": row["google_sheet_row"],
            "google_sheet_row": row["google_sheet_row"],
            "trip_number": row["trip_number"],
            "db_task_id": row["id"],
            "updated_at": row["updated_at"],
            "status": row["status"] or "",
            "ТС": row["plate_number"] or "",
            "Телефон": row["driver_phone"] or "",
            "ФИО": row["driver_name"] or "",
            "КА": row["carrier_name"] or "",
            "loads": self._route_points_to_view_points(route_points.get((task_id, "load"), [])),
            "unloads": self._route_points_to_view_points(route_points.get((task_id, "unload"), [])),
            "processed_unloads": self._processed_flags(route_points.get((task_id, "unload"), [])),
            "Погрузка": self._route_points_to_gui_blocks(route_points.get((task_id, "load"), []), "Погрузка"),
            "Выгрузка": self._route_points_to_gui_blocks(route_points.get((task_id, "unload"), []), "Выгрузка"),
            "processed": self._processed_flags(route_points.get((task_id, "unload"), [])),
            "raw_load": row["raw_load"] or "",
            "raw_unload": row["raw_unload"] or "",
        }

        if row["monitoring_id"] is not None:
            result["id"] = row["monitoring_id"]
        if row["highlight_until"]:
            result["highlight_until"] = row["highlight_until"]

        navigation_row = latest_navigation.get(task_id)
        result["navigation"] = self._navigation_to_view(navigation_row)
        navigation = self._navigation_to_gui_fields(navigation_row)
        if navigation:
            result.update(navigation)

        estimate_row = latest_estimates.get(task_id)
        result["route_estimate"] = self._route_estimate_to_view(estimate_row)
        estimate = self._route_estimate_to_gui_field(estimate_row)
        if estimate:
            result["Маршрут"] = estimate

        return result

    @staticmethod
    def _route_points_to_view_points(rows: list[dict]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            date, time = PostgresTaskReader._split_datetime_text(row["scheduled_time"])
            result.append(
                {
                    "sequence": row["sequence"],
                    "address": row["location"] or "",
                    "date": date,
                    "time": time,
                    "comment": row["comment"] or "",
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "is_processed": bool(row["is_processed"]),
                }
            )
        return result

    def _route_points_to_gui_blocks(self, rows: list[dict], prefix: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
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

    @staticmethod
    def _processed_flags(rows: list[dict]) -> list[bool]:
        return [bool(row["is_processed"]) for row in rows]

    @staticmethod
    def _navigation_to_gui_fields(row: dict | None) -> dict[str, Any]:
        if row is None:
            return {}

        result: dict[str, Any] = {
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

    @staticmethod
    def _navigation_to_view(row: dict | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "geo_text": row["geo_text"] or "",
            "geo_zone": row["geo_zona"] or "",
            "coordinates": row["coordinates"] or "",
            "speed_kmh": row["speed_kmh"],
            "gps_fix_text": row["gps_fix_text"] or "",
            "gps_fix_age_seconds": row["gps_fix_age_seconds"],
            "has_fresh_coordinates": bool(row["has_fresh_coordinates"]),
        }

    @staticmethod
    def _route_estimate_to_gui_field(row: dict | None) -> dict[str, Any]:
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
    def _route_estimate_to_view(row: dict | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "distance_km": row["distance_km"],
            "duration_minutes": row["duration_minutes"],
            "arrival_time": row["arrival_time"] or "",
            "on_time": bool(row["on_time"]),
            "buffer_minutes": row["buffer_minutes"],
            "time_buffer_text": row["time_buffer_text"] or "",
        }

    @staticmethod
    def _split_datetime_text(value: Any) -> tuple[str, str]:
        text = str(value or "").strip()
        if not text:
            return "", ""
        parts = text.split()
        if len(parts) >= 2:
            return parts[0], parts[1]
        if ":" in text:
            return "", text
        return text, ""
