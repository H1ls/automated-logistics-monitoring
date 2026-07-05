from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Callable

from Navigation_Bot.core.logging import noop_log, normalize_log_func


def _now_text() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def _to_row(item: Any) -> dict:
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    raise TypeError("history item must be dataclass or dict")


def _to_int_or_none(value: Any) -> int | None:
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


def _parse_coordinates(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if not text or "," not in text:
        return None, None
    left, right = text.split(",", 1)
    try:
        return float(left.strip()), float(right.strip())
    except ValueError:
        return None, None


class _PostgresHistoryBase:
    def __init__(self, connection: Any, log: Callable[[str], None] | None = None):
        self.connection = connection
        self.log = normalize_log_func(log or noop_log)

    def _log(self, msg: str) -> None:
        self.log(msg)

    def _task_id_by_trip_number(self, value: int | str | None) -> int | None:
        parsed = _to_int_or_none(value)
        if parsed is None:
            return None
        row = self.connection.execute("SELECT id FROM tasks WHERE trip_number = %s", (parsed,)).fetchone()
        return int(row["id"]) if row is not None else None

    def _task_id_by_google_sheet_row(self, value: int | str | None) -> int | None:
        parsed = _to_int_or_none(value)
        if parsed is None:
            return None
        row = self.connection.execute("SELECT id FROM tasks WHERE google_sheet_row = %s", (parsed,)).fetchone()
        return int(row["id"]) if row is not None else None

    @staticmethod
    def _trip_number_from_row(row: dict[str, Any]) -> Any:
        return row.get("trip_number")


class PostgresStatusEventService(_PostgresHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        task_id = self._task_id_by_trip_number(self._trip_number_from_row(row))
        if task_id is None:
            self._log(f"PostgreSQL status event skipped: task not found for trip_number={self._trip_number_from_row(row)}")
            return

        created_at = row.get("created_at") or _now_text()
        with self.connection.transaction():
            if self.connection.execute(
                """
                SELECT 1 FROM status_events
                WHERE task_id = %s AND event_type = %s AND field_name = %s
                  AND created_at = %s AND message = %s
                """,
                (task_id, row.get("event_type") or "", row.get("field_name") or "", created_at, row.get("message") or ""),
            ).fetchone():
                return
            inserted = self.connection.execute(
                """
                INSERT INTO status_events(
                    task_id, user_id, event_type, field_name, old_value, new_value, message, source, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    task_id,
                    row.get("user_id"),
                    row.get("event_type") or "",
                    row.get("field_name") or "",
                    row.get("old_value"),
                    row.get("new_value"),
                    row.get("message") or "",
                    row.get("source") or "user",
                    created_at,
                ),
            ).fetchone()
        if hasattr(item, "id"):
            item.id = int(inserted["id"])
        if hasattr(item, "created_at") and not getattr(item, "created_at"):
            item.created_at = created_at

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        task_id = self._task_id_by_trip_number(trip_number)
        if task_id is None:
            return []
        rows = self.connection.execute(
            """
            SELECT se.*, t.google_sheet_row, t.trip_number
            FROM status_events se
            JOIN tasks t ON t.id = se.task_id
            WHERE se.task_id = %s
            ORDER BY se.created_at
            """,
            (task_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "trip_number": row["trip_number"],
                "event_type": row["event_type"],
                "field_name": row["field_name"],
                "old_value": row["old_value"],
                "new_value": row["new_value"],
                "message": row["message"],
                "created_at": row["created_at"],
                "source": row["source"],
            }
            for row in rows
        ]


class PostgresRouteEstimateHistoryService(_PostgresHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        task_id = self._task_id_by_trip_number(self._trip_number_from_row(row))
        if task_id is None:
            self._log(f"PostgreSQL route estimate skipped: task not found for trip_number={self._trip_number_from_row(row)}")
            return
        calculated_at = row.get("calculated_at") or _now_text()
        with self.connection.transaction():
            if self.connection.execute(
                """
                SELECT 1 FROM route_estimates
                WHERE task_id = %s AND target_sequence = %s AND calculated_at = %s AND arrival_time = %s
                """,
                (task_id, int(row.get("target_sequence") or 0), calculated_at, row.get("arrival_time") or ""),
            ).fetchone():
                return
            inserted = self.connection.execute(
                """
                INSERT INTO route_estimates(
                    task_id, target_sequence, distance_km, duration_minutes,
                    arrival_time, on_time, buffer_minutes, time_buffer_text, calculated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    task_id,
                    int(row.get("target_sequence") or 0),
                    float(row.get("distance_km") or 0),
                    int(row.get("duration_minutes") or 0),
                    row.get("arrival_time") or "",
                    bool(row.get("on_time")),
                    int(row.get("buffer_minutes") or 0),
                    row.get("time_buffer_text") or "",
                    calculated_at,
                ),
            ).fetchone()
        if hasattr(item, "id"):
            item.id = int(inserted["id"])
        if hasattr(item, "calculated_at") and not getattr(item, "calculated_at"):
            item.calculated_at = calculated_at

    def append_estimate(self, estimate: Any) -> None:
        self.append(estimate)

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        task_id = self._task_id_by_trip_number(trip_number)
        if task_id is None:
            return []
        rows = self.connection.execute(
            """
            SELECT re.*, t.google_sheet_row, t.trip_number
            FROM route_estimates re
            JOIN tasks t ON t.id = re.task_id
            WHERE re.task_id = %s
            ORDER BY re.calculated_at
            """,
            (task_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "trip_number": row["trip_number"],
                "target_sequence": row["target_sequence"],
                "distance_km": row["distance_km"],
                "duration_minutes": row["duration_minutes"],
                "arrival_time": row["arrival_time"],
                "on_time": bool(row["on_time"]),
                "buffer_minutes": row["buffer_minutes"],
                "time_buffer_text": row["time_buffer_text"],
                "calculated_at": row["calculated_at"],
            }
            for row in rows
        ]


class PostgresNoteHistoryService(_PostgresHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        task_id = self._task_id_by_trip_number(self._trip_number_from_row(row))
        if task_id is None:
            self._log(f"PostgreSQL note skipped: task not found for trip_number={self._trip_number_from_row(row)}")
            return
        created_at = row.get("created_at") or _now_text()
        media_paths = row.get("media_paths")
        media_path = row.get("media_path")
        if media_paths is not None:
            media_path = "\n".join(str(path) for path in media_paths)
        with self.connection.transaction():
            if self.connection.execute(
                """
                SELECT 1 FROM task_notes
                WHERE task_id = %s AND created_at = %s AND text = %s AND media_path IS NOT DISTINCT FROM %s
                """,
                (task_id, created_at, row.get("text") or "", media_path),
            ).fetchone():
                return
            inserted = self.connection.execute(
                """
                INSERT INTO task_notes(
                    text, task_id, author_user_id, author, media_type, media_path,
                    is_important, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (
                    row.get("text") or "",
                    task_id,
                    row.get("author_user_id"),
                    row.get("author") or "user",
                    row.get("media_type") or "",
                    media_path,
                    bool(row.get("is_important")),
                    created_at,
                ),
            ).fetchone()
        if hasattr(item, "id"):
            item.id = int(inserted["id"])
        if hasattr(item, "created_at") and not getattr(item, "created_at"):
            item.created_at = created_at

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        task_id = self._task_id_by_trip_number(trip_number)
        if task_id is None:
            return []
        rows = self.connection.execute(
            """
            SELECT tn.*, t.google_sheet_row, t.trip_number
            FROM task_notes tn
            JOIN tasks t ON t.id = tn.task_id
            WHERE tn.task_id = %s
            ORDER BY tn.created_at
            """,
            (task_id,),
        ).fetchall()
        return [self._note_row_to_dict(row) for row in rows]

    @staticmethod
    def _note_row_to_dict(row: dict) -> dict:
        media_path = row["media_path"] or ""
        media_paths = [path for path in media_path.splitlines() if path]
        return {
            "id": row["id"],
            "trip_number": row["trip_number"],
            "created_at": row["created_at"],
            "author": row["author"],
            "text": row["text"],
            "media_paths": media_paths,
            "media_type": row["media_type"] or "",
            "is_important": bool(row["is_important"]),
        }


class PostgresNavigationHistoryService(_PostgresHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        task_id = self._task_id_by_trip_number(self._trip_number_from_row(row))
        vehicle_id = self._vehicle_id(row, task_id)
        if vehicle_id is None:
            self._log("PostgreSQL navigation skipped: vehicle not found")
            return
        collected_at = row.get("collected_at") or _now_text()
        latitude, longitude = _parse_coordinates(row.get("coordinates"))
        with self.connection.transaction():
            if self.connection.execute(
                """
                SELECT 1 FROM vehicle_navigation_history
                WHERE vehicle_id = %s AND task_id IS NOT DISTINCT FROM %s AND collected_at = %s
                  AND coordinates = %s AND geo_text = %s
                """,
                (vehicle_id, task_id, collected_at, row.get("coordinates") or "", row.get("geo_text") or ""),
            ).fetchone():
                return
            inserted = self.connection.execute(
                """
                INSERT INTO vehicle_navigation_history(
                    vehicle_id, task_id, latitude, longitude, coordinates,
                    geo_text, geo_zona, speed_kmh, gps_fix_text,
                    gps_fix_age_seconds, has_fresh_coordinates, is_navigation_stale, collected_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    vehicle_id,
                    task_id,
                    latitude,
                    longitude,
                    row.get("coordinates") or "",
                    row.get("geo_text") or "",
                    row.get("geo_zona") or "",
                    row.get("speed_kmh"),
                    row.get("gps_fix_text") or "",
                    row.get("gps_fix_age_seconds"),
                    bool(row.get("has_fresh_coordinates")),
                    bool(row.get("is_navigation_stale")),
                    collected_at,
                ),
            ).fetchone()
        if hasattr(item, "id"):
            item.id = int(inserted["id"])
        if hasattr(item, "collected_at") and not getattr(item, "collected_at"):
            item.collected_at = collected_at

    def append_snapshot(self, snapshot: Any) -> None:
        self.append(snapshot)

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        task_id = self._task_id_by_trip_number(trip_number)
        if task_id is None:
            return []
        rows = self.connection.execute(
            """
            SELECT vnh.*, v.plate_number, v.monitoring_id, t.google_sheet_row, t.trip_number
            FROM vehicle_navigation_history vnh
            JOIN vehicles v ON v.id = vnh.vehicle_id
            LEFT JOIN tasks t ON t.id = vnh.task_id
            WHERE vnh.task_id = %s
            ORDER BY vnh.collected_at
            """,
            (task_id,),
        ).fetchall()
        return [self._navigation_row_to_dict(row) for row in rows]

    def get_by_vehicle_monitoring_id(self, vehicle_monitoring_id: int | str | None) -> list[dict]:
        parsed = _to_int_or_none(vehicle_monitoring_id)
        if parsed is None:
            return []
        rows = self.connection.execute(
            """
            SELECT vnh.*, v.plate_number, v.monitoring_id, t.google_sheet_row, t.trip_number
            FROM vehicle_navigation_history vnh
            JOIN vehicles v ON v.id = vnh.vehicle_id
            LEFT JOIN tasks t ON t.id = vnh.task_id
            WHERE v.monitoring_id = %s
            ORDER BY vnh.collected_at
            """,
            (parsed,),
        ).fetchall()
        return [self._navigation_row_to_dict(row) for row in rows]

    def _vehicle_id(self, row: dict, task_id: int | None) -> int | None:
        if task_id is not None:
            task_row = self.connection.execute("SELECT vehicle_id FROM tasks WHERE id = %s", (task_id,)).fetchone()
            if task_row is not None and task_row["vehicle_id"] is not None:
                return int(task_row["vehicle_id"])
        monitoring_id = _to_int_or_none(row.get("vehicle_monitoring_id"))
        plate = str(row.get("vehicle_plate") or "").strip()
        if monitoring_id is not None:
            found = self.connection.execute("SELECT id FROM vehicles WHERE monitoring_id = %s", (monitoring_id,)).fetchone()
            if found is not None:
                return int(found["id"])
        if plate:
            found = self.connection.execute("SELECT id FROM vehicles WHERE plate_number = %s", (plate,)).fetchone()
            if found is not None:
                return int(found["id"])
        plate = plate or (f"monitoring_id:{monitoring_id}" if monitoring_id is not None else "unknown")
        with self.connection.transaction():
            inserted = self.connection.execute(
                """
                INSERT INTO vehicles(plate_number, monitoring_id)
                VALUES (%s, %s)
                ON CONFLICT(plate_number) DO UPDATE SET
                    monitoring_id = COALESCE(excluded.monitoring_id, vehicles.monitoring_id),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (plate, monitoring_id),
            ).fetchone()
        return int(inserted["id"])

    @staticmethod
    def _navigation_row_to_dict(row: dict) -> dict:
        return {
            "id": row["id"],
            "trip_number": row["trip_number"],
            "vehicle_plate": row["plate_number"] or "",
            "vehicle_monitoring_id": row["monitoring_id"],
            "collected_at": row["collected_at"],
            "geo_text": row["geo_text"],
            "geo_zona": row["geo_zona"],
            "coordinates": row["coordinates"],
            "speed_kmh": row["speed_kmh"],
            "gps_fix_text": row["gps_fix_text"],
            "gps_fix_age_seconds": row["gps_fix_age_seconds"],
            "has_fresh_coordinates": bool(row["has_fresh_coordinates"]),
            "is_navigation_stale": bool(row["is_navigation_stale"]),
        }
