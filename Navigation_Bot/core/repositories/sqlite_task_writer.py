from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.repositories.sqlite_route_point_repository import SqliteRoutePointRepository
from Navigation_Bot.core.repositories.sqlite_status_event_repository import SqliteStatusEventRepository
from Navigation_Bot.core.repositories.sqlite_task_lookup import SqliteTaskLookup

TERMINAL_TASK_STATUSES = {"completed", "archived", "cancelled"}

"""
Запись рейсов в SQLite.
SqliteTaskWriter принимает старую dict-строку из GUI/Google, превращает ее в доменный Task и раскладывает данные 
по нормализованным таблицам: tasks, carriers, vehicles,drivers и route_points. 
Фасад репозитория вызывает этот класс, чтобы не держать SQL-запись внутри себя.
"""


@dataclass(slots=True)
class SqliteTaskWriter:
    """Отвечает за создание/обновление рейса и связанных справочников."""

    connection: sqlite3.Connection
    source_key: str = ""

    def upsert_from_row(self, row: dict[str, Any], *, source: str = "user") -> dict[str, int] | None:
        """Создает или обновляет рейс из legacy-строки и возвращает его ключи."""
        if not isinstance(row, dict):
            return None

        task = TaskMapper.from_dict(row)
        lookup = self._lookup()
        # index пока остается legacy-именем строки Google; google_sheet_row хранит тот же смысл явно.
        google_sheet_row = self._positive_int_or_none(row.get("google_sheet_row")) or self._positive_int_or_none(row.get("index"))
        # trip_number - внутренний номер рейса, не завязанный на строку Google.
        trip_number = self._resolve_trip_number_for_upsert(row, task, google_sheet_row, source, lookup)

        with self.connection:
            # Справочники upsert-ятся до tasks, чтобы сохранить FK-ссылки.
            carrier_id = self._upsert_carrier(task.carrier.name if task.carrier else "")
            vehicle_id = self._upsert_vehicle(
                plate_number=task.vehicle.plate_number,
                monitoring_id=task.vehicle.monitoring_id,
                carrier_id=carrier_id,
                brand=task.vehicle.brand,
                model=task.vehicle.model,
                is_active=task.vehicle.is_active,
            )
            driver_id = self._upsert_driver(
                full_name=task.driver.full_name,
                phone=task.driver.phone,
                carrier_id=carrier_id,
                is_active=task.driver.is_active,
            )

            planned_start_at = self._first_planned_time(task.route_plan.loads)
            planned_end_at = self._last_planned_time(task.route_plan.unloads)

            existing_task_id = lookup.task_id_by_trip_number(trip_number)
            if (existing_task_id is not None
                    and source == "google"
                    and self._is_terminal_task(existing_task_id)
                    and self._same_task_signature(existing_task_id, task)):
                row["trip_number"] = trip_number
                row["task_index"] = trip_number
                row["google_sheet_row"] = google_sheet_row
                row["db_task_id"] = existing_task_id
                return {"task_id": existing_task_id, "trip_number": trip_number, "task_index": trip_number}

            if existing_task_id is None:
                # Новый рейс: создаем строку tasks и потом привязываем route_points.
                cursor = self.connection.execute(
                    """
                    INSERT INTO tasks (
                        trip_number, google_sheet_row, vehicle_id, driver_id, carrier_id,
                        status, planned_start_at, planned_end_at, actual_start_at, actual_end_at,
                        raw_load, raw_unload, comm_load, comm_unload, highlight_until,
                        google_worksheet_title
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trip_number,
                        google_sheet_row,
                        vehicle_id,
                        driver_id,
                        carrier_id,
                        self._status_from_row(row),
                        planned_start_at,
                        planned_end_at,
                        row.get("actual_start_at"),
                        row.get("actual_end_at"),
                        task.raw_load,
                        task.raw_unload,
                        task.comm_load,
                        task.comm_unload,
                        task.highlight_until,
                        self.source_key or row.get("google_worksheet_title"),
                    ),
                )
                task_id = int(cursor.lastrowid)
            else:
                # Существующий рейс: обновляем поля, но сохраняем тот же tasks.id/trip_number.
                task_id = existing_task_id
                self.connection.execute(
                    """
                    UPDATE tasks
                    SET google_sheet_row = ?,
                        vehicle_id = ?,
                        driver_id = ?,
                        carrier_id = ?,
                        status = ?,
                        planned_start_at = ?,
                        planned_end_at = ?,
                        raw_load = ?,
                        raw_unload = ?,
                        comm_load = ?,
                        comm_unload = ?,
                        highlight_until = ?,
                        actual_start_at = ?,
                        actual_end_at = ?,
                        google_worksheet_title = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        google_sheet_row,
                        vehicle_id,
                        driver_id,
                        carrier_id,
                        self._status_from_row(row),
                        planned_start_at,
                        planned_end_at,
                        task.raw_load,
                        task.raw_unload,
                        task.comm_load,
                        task.comm_unload,
                        task.highlight_until,
                        row.get("actual_start_at"),
                        row.get("actual_end_at"),
                        self.source_key or row.get("google_worksheet_title"),
                        task_id,
                    ),
                )

            route_points = SqliteRoutePointRepository(self.connection)
            route_points.sync_route_points(task_id, "load", task.route_plan.loads, task.processing.processed_unloads,
                                           source)
            route_points.sync_route_points(task_id, "unload", task.route_plan.unloads,
                                           task.processing.processed_unloads, source)

        # Обогащаем исходный dict, чтобы GUI сразу видел реальные ключи БД без reload.
        row["trip_number"] = trip_number
        row["task_index"] = trip_number
        row["google_sheet_row"] = google_sheet_row
        row["db_task_id"] = task_id
        return {"task_id": task_id, "trip_number": trip_number, "task_index": trip_number}

    def _resolve_trip_number_for_upsert(
            self,
            row: dict[str, Any],
            task: Any,
            google_sheet_row: int | None,
            source: str,
            lookup: SqliteTaskLookup,
    ) -> int:
        explicit = lookup.to_int_or_none(row.get("trip_number")) or lookup.to_int_or_none(row.get("task_index"))
        db_task_id = lookup.to_int_or_none(row.get("db_task_id"))
        if explicit is not None or db_task_id is not None or source != "google" or google_sheet_row is None:
            return lookup.resolve_trip_number(row, google_sheet_row)

        active_task_id = self._task_id_by_google_sheet_row(google_sheet_row, terminal=False)
        if active_task_id is not None:
            if self._looks_like_reused_google_row(active_task_id, task):
                self._archive_replaced_google_row(active_task_id)
                return lookup.next_trip_number()
            return self._trip_number_by_task_id(active_task_id) or lookup.next_trip_number()

        terminal_task_id = self._task_id_by_google_sheet_row(google_sheet_row, terminal=True)
        if terminal_task_id is not None and self._same_task_signature(terminal_task_id, task):
            return self._trip_number_by_task_id(terminal_task_id) or lookup.next_trip_number()

        return lookup.next_trip_number()

    def _task_id_by_google_sheet_row(self, google_sheet_row: int, *, terminal: bool) -> int | None:
        status_filter = "IN" if terminal else "NOT IN"
        row = self.connection.execute(
            f"""
            SELECT id
            FROM tasks
            WHERE google_sheet_row = ?
              AND status {status_filter} ('completed', 'archived', 'cancelled')
              AND (? = '' OR google_worksheet_title = ? OR google_worksheet_title IS NULL)
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (google_sheet_row, self.source_key, self.source_key),
        ).fetchone()
        return int(row["id"]) if row is not None else None

    def _trip_number_by_task_id(self, task_id: int) -> int | None:
        row = self.connection.execute("SELECT trip_number FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return int(row["trip_number"]) if row is not None and row["trip_number"] is not None else None

    def _same_task_signature(self, task_id: int, task: Any) -> bool:
        return self._db_task_signature(task_id) == self._incoming_task_signature(task)

    def _looks_like_reused_google_row(self, task_id: int, task: Any) -> bool:
        old_plate, old_load, old_unload = self._db_task_signature(task_id)
        new_plate, new_load, new_unload = self._incoming_task_signature(task)
        if not old_plate or not new_plate:
            return False
        return old_plate != new_plate and (old_load != new_load or old_unload != new_unload)

    def _db_task_signature(self, task_id: int) -> tuple[str, str, str]:
        row = self.connection.execute(
            """
            SELECT v.plate_number, t.raw_load, t.raw_unload
            FROM tasks t
            LEFT JOIN vehicles v ON v.id = t.vehicle_id
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is None:
            return "", "", ""
        return (
            self._signature_text(row["plate_number"]),
            self._signature_text(row["raw_load"]),
            self._signature_text(row["raw_unload"]),
        )

    def _incoming_task_signature(self, task: Any) -> tuple[str, str, str]:
        return (
            self._signature_text(getattr(task.vehicle, "plate_number", "")),
            self._signature_text(getattr(task, "raw_load", "")),
            self._signature_text(getattr(task, "raw_unload", "")),
        )

    def _archive_replaced_google_row(self, task_id: int) -> None:
        old_status_row = self.connection.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        old_status = old_status_row["status"] if old_status_row is not None else ""
        self.connection.execute(
            """
            UPDATE tasks
            SET status = 'completed',
                actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP),
                completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                completion_source = 'google_replaced',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (task_id,),
        )
        SqliteStatusEventRepository(self.connection).append_task_event(
            task_id=task_id,
            event_type="google_row_reused",
            field_name="status",
            old_value=old_status,
            new_value="completed",
            message="Google row was reused for another trip; previous trip archived",
            source="google_replaced",
        )

    @staticmethod
    def _signature_text(value: Any) -> str:
        return " ".join(str(value or "").lower().split())

    def mark_missing_rows_inactive(self, rows: list[dict]) -> None:
        """Помечает completed те Google-рейсы, которых нет в новом активном наборе."""
        lookup = self._lookup()
        active_indexes = {
            lookup.to_int_or_none(row.get("index"))
            for row in rows
            if isinstance(row, dict) and lookup.to_int_or_none(row.get("index")) is not None
        }
        if not active_indexes:
            with self.connection:
                self.connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'completed',
                        actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP),
                        completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                        completion_source = 'google',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ? = '' OR google_worksheet_title = ? OR google_worksheet_title IS NULL
                    """,
                    (self.source_key, self.source_key),
                )
            return

        placeholders = ",".join("?" for _ in active_indexes)
        with self.connection:
            self.connection.execute(
                f"""
                UPDATE tasks
                SET status = 'completed',
                    actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP),
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                    completion_source = 'google',
                    updated_at = CURRENT_TIMESTAMP
                WHERE google_sheet_row IS NOT NULL
                  AND (? = '' OR google_worksheet_title = ? OR google_worksheet_title IS NULL)
                  AND google_sheet_row NOT IN ({placeholders})
                """,
                (self.source_key, self.source_key, *tuple(active_indexes)),
            )

    def mark_index_inactive(self, index_key: int) -> None:
        """Помечает один рейс completed по legacy index/google_sheet_row или trip_number."""
        parsed = self._lookup().to_int_or_none(index_key)
        if parsed is None:
            return
        with self.connection:
            self.connection.execute(
                """
                UPDATE tasks
                SET status = 'completed',
                    actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP),
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                    completion_source = 'user',
                    updated_at = CURRENT_TIMESTAMP
                WHERE (google_sheet_row = ? OR trip_number = ?)
                  AND (? = '' OR google_worksheet_title = ? OR google_worksheet_title IS NULL)
                """,
                (parsed, parsed, self.source_key, self.source_key),
            )

    def mark_task_completed(self, row_identity: int, *, source: str = "user") -> bool:
        """Marks one task completed by trip_number or google_sheet_row."""
        parsed = self._lookup().to_int_or_none(row_identity)
        if parsed is None:
            return False

        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE tasks
                SET status = 'completed',
                    actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP),
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                    completion_source = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE (google_sheet_row = ? OR trip_number = ?)
                  AND (? = '' OR google_worksheet_title = ? OR google_worksheet_title IS NULL)
                """,
                (source, parsed, parsed, self.source_key, self.source_key),
            )
        return cursor.rowcount > 0

    def _is_terminal_task(self, task_id: int) -> bool:
        row = self.connection.execute(
            "SELECT status FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return False
        return str(row["status"] or "").strip().lower() in TERMINAL_TASK_STATUSES

    def _upsert_carrier(self, name: str) -> int | None:
        """Создает перевозчика или обновляет updated_at у существующего."""
        name = str(name or "").strip()
        if not name:
            return None

        self.connection.execute(
            """
            INSERT INTO carriers(name)
            VALUES (?)
            ON CONFLICT(name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """,
            (name,),
        )
        return self._lookup().fetch_id("SELECT id FROM carriers WHERE name = ?", (name,))

    def _upsert_vehicle(
            self,
            *,
            plate_number: str,
            monitoring_id: int | None,
            carrier_id: int | None,
            brand: str,
            model: str,
            is_active: bool,
    ) -> int | None:
        """Создает/обновляет ТС по уникальному номеру автомобиля."""
        plate_number = str(plate_number or "").strip()
        if not plate_number:
            return None

        self.connection.execute(
            """
            INSERT INTO vehicles(plate_number, monitoring_id, carrier_id, brand, model, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(plate_number) DO UPDATE SET
                monitoring_id = COALESCE(excluded.monitoring_id, vehicles.monitoring_id),
                carrier_id = excluded.carrier_id,
                brand = excluded.brand,
                model = excluded.model,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (plate_number, monitoring_id, carrier_id, brand or "", model or "", int(bool(is_active))),
        )
        return self._lookup().fetch_id("SELECT id FROM vehicles WHERE plate_number = ?", (plate_number,))

    def _upsert_driver(self, *, full_name: str, phone: str, carrier_id: int | None, is_active: bool) -> int | None:
        """Создает/обновляет водителя по паре ФИО + телефон."""
        full_name = str(full_name or "").strip()
        phone = str(phone or "").strip()
        if not full_name and not phone:
            return None

        existing_id = self._lookup().fetch_id(
            "SELECT id FROM drivers WHERE full_name = ? AND phone = ?",
            (full_name, phone),
        )
        if existing_id is None:
            cursor = self.connection.execute(
                """
                INSERT INTO drivers(full_name, phone, carrier_id, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (full_name, phone, carrier_id, int(bool(is_active))),
            )
            return int(cursor.lastrowid)

        self.connection.execute(
            """
            UPDATE drivers
            SET carrier_id = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (carrier_id, int(bool(is_active)), existing_id),
        )
        return existing_id

    def _lookup(self) -> SqliteTaskLookup:
        """Создает lookup, привязанный к текущему листу Google."""
        return SqliteTaskLookup(self.connection, self.source_key)

    def _positive_int_or_none(self, value: Any) -> int | None:
        parsed = self._lookup().to_int_or_none(value)
        if parsed is None or parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _first_planned_time(points: list[Any]) -> str | None:
        """Берет плановое начало рейса из первой точки погрузки."""
        if not points:
            return None
        return points[0].planned_datetime_text() or None

    @staticmethod
    def _last_planned_time(points: list[Any]) -> str | None:
        """Берет плановое окончание рейса из последней точки выгрузки."""
        if not points:
            return None
        return points[-1].planned_datetime_text() or None

    @staticmethod
    def _status_from_row(row: dict[str, Any]) -> str:
        """Нормализует статус рейса, если в legacy-строке он отсутствует."""
        status = str(row.get("status") or "").strip()
        return status or "active"
