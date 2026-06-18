from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.repositories.postgres_route_point_repository import PostgresRoutePointRepository
from Navigation_Bot.core.repositories.postgres_task_lookup import PostgresTaskLookup


class TaskConflictError(RuntimeError):
    def __init__(self, *, task_id: int, expected_updated_at: Any, current_updated_at: Any):
        self.task_id = task_id
        self.expected_updated_at = expected_updated_at
        self.current_updated_at = current_updated_at
        super().__init__(f"task_conflict: task_id={task_id}")


@dataclass(slots=True)
class PostgresTaskWriter:
    connection: Any
    source_key: str = ""

    def upsert_from_row(self, row: dict[str, Any], *, source: str = "user") -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None

        task = TaskMapper.from_dict(row)
        lookup = self._lookup()
        google_sheet_row = self._positive_int_or_none(row.get("google_sheet_row")) or self._positive_int_or_none(row.get("index"))
        trip_number = lookup.resolve_trip_number(row, google_sheet_row)

        with self.connection.transaction():
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
            expected_updated_at = row.get("updated_at")
            created = existing_task_id is None

            if existing_task_id is None:
                inserted = self._insert_task(
                    trip_number=trip_number,
                    google_sheet_row=google_sheet_row,
                    vehicle_id=vehicle_id,
                    driver_id=driver_id,
                    carrier_id=carrier_id,
                    status=self._status_from_row(row),
                    planned_start_at=planned_start_at,
                    planned_end_at=planned_end_at,
                    actual_start_at=row.get("actual_start_at"),
                    actual_end_at=row.get("actual_end_at"),
                    raw_load=task.raw_load,
                    raw_unload=task.raw_unload,
                    comm_load=task.comm_load,
                    comm_unload=task.comm_unload,
                    highlight_until=task.highlight_until,
                    google_worksheet_title=self.source_key or row.get("google_worksheet_title"),
                )
                task_id = int(inserted["id"])
                updated_at = inserted["updated_at"]
            else:
                task_id = existing_task_id
                updated_at = self._update_task(
                    task_id=task_id,
                    expected_updated_at=expected_updated_at,
                    google_sheet_row=google_sheet_row,
                    vehicle_id=vehicle_id,
                    driver_id=driver_id,
                    carrier_id=carrier_id,
                    status=self._status_from_row(row),
                    planned_start_at=planned_start_at,
                    planned_end_at=planned_end_at,
                    actual_start_at=row.get("actual_start_at"),
                    actual_end_at=row.get("actual_end_at"),
                    raw_load=task.raw_load,
                    raw_unload=task.raw_unload,
                    comm_load=task.comm_load,
                    comm_unload=task.comm_unload,
                    highlight_until=task.highlight_until,
                    google_worksheet_title=self.source_key or row.get("google_worksheet_title"),
                )

            route_points = PostgresRoutePointRepository(self.connection)
            route_points.sync_route_points(task_id, "load", task.route_plan.loads, task.processing.processed_unloads, source)
            route_points.sync_route_points(task_id, "unload", task.route_plan.unloads, task.processing.processed_unloads, source)

        row["trip_number"] = trip_number
        row["google_sheet_row"] = google_sheet_row
        row["db_task_id"] = task_id
        row["updated_at"] = updated_at
        return {"task_id": task_id, "trip_number": trip_number, "updated_at": updated_at, "created": created}

    def mark_index_inactive(self, index_key: int) -> None:
        parsed = self._lookup().to_int_or_none(index_key)
        if parsed is None:
            return
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE tasks
                SET status = 'completed',
                    actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP::text),
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP::text),
                    completion_source = 'user',
                    updated_at = CURRENT_TIMESTAMP
                WHERE (google_sheet_row = %s OR trip_number = %s)
                  AND (%s = '' OR google_worksheet_title = %s OR google_worksheet_title IS NULL)
                """,
                (parsed, parsed, self.source_key, self.source_key),
            )

    def mark_task_completed(self, row_identity: int, *, source: str = "user") -> bool:
        parsed = self._lookup().to_int_or_none(row_identity)
        if parsed is None:
            return False

        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                UPDATE tasks
                SET status = 'completed',
                    actual_end_at = COALESCE(actual_end_at, CURRENT_TIMESTAMP::text),
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP::text),
                    completion_source = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE (google_sheet_row = %s OR trip_number = %s)
                  AND (%s = '' OR google_worksheet_title = %s OR google_worksheet_title IS NULL)
                """,
                (source, parsed, parsed, self.source_key, self.source_key),
            )
        return cursor.rowcount > 0

    def _insert_task(self, **values: Any) -> dict[str, Any]:
        return self.connection.execute(
            """
            INSERT INTO tasks (
                trip_number, google_sheet_row, vehicle_id, driver_id, carrier_id,
                status, planned_start_at, planned_end_at, actual_start_at, actual_end_at,
                raw_load, raw_unload, comm_load, comm_unload, highlight_until,
                google_worksheet_title
            )
            VALUES (
                %(trip_number)s, %(google_sheet_row)s, %(vehicle_id)s, %(driver_id)s, %(carrier_id)s,
                %(status)s, %(planned_start_at)s, %(planned_end_at)s, %(actual_start_at)s, %(actual_end_at)s,
                %(raw_load)s, %(raw_unload)s, %(comm_load)s, %(comm_unload)s, %(highlight_until)s,
                %(google_worksheet_title)s
            )
            RETURNING id, updated_at
            """,
            values,
        ).fetchone()

    def _update_task(self, *, task_id: int, expected_updated_at: Any = None, **values: Any) -> Any:
        params = {**values, "task_id": task_id, "expected_updated_at": expected_updated_at}
        row = self.connection.execute(
            """
            UPDATE tasks
            SET google_sheet_row = %(google_sheet_row)s,
                vehicle_id = %(vehicle_id)s,
                driver_id = %(driver_id)s,
                carrier_id = %(carrier_id)s,
                status = %(status)s,
                planned_start_at = %(planned_start_at)s,
                planned_end_at = %(planned_end_at)s,
                raw_load = %(raw_load)s,
                raw_unload = %(raw_unload)s,
                comm_load = %(comm_load)s,
                comm_unload = %(comm_unload)s,
                highlight_until = %(highlight_until)s,
                actual_start_at = %(actual_start_at)s,
                actual_end_at = %(actual_end_at)s,
                google_worksheet_title = %(google_worksheet_title)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(task_id)s
              AND (
                  %(expected_updated_at)s::timestamptz IS NULL
                  OR updated_at = %(expected_updated_at)s::timestamptz
              )
            RETURNING updated_at
            """,
            params,
        ).fetchone()
        if row is not None:
            return row["updated_at"]

        current = self.connection.execute(
            "SELECT updated_at FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()
        raise TaskConflictError(
            task_id=task_id,
            expected_updated_at=expected_updated_at,
            current_updated_at=current["updated_at"] if current is not None else None,
        )

    def _upsert_carrier(self, name: str) -> int | None:
        name = str(name or "").strip()
        if not name:
            return None
        row = self.connection.execute(
            """
            INSERT INTO carriers(name)
            VALUES (%s)
            ON CONFLICT(name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (name,),
        ).fetchone()
        return int(row["id"])

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
        plate_number = str(plate_number or "").strip()
        if not plate_number:
            return None

        if monitoring_id is not None:
            existing = self._lookup().fetch_id("SELECT id FROM vehicles WHERE monitoring_id = %s", (monitoring_id,))
            if existing is not None:
                self.connection.execute(
                    """
                    UPDATE vehicles
                    SET carrier_id = COALESCE(%s, carrier_id),
                        brand = COALESCE(NULLIF(%s, ''), brand),
                        model = COALESCE(NULLIF(%s, ''), model),
                        is_active = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (carrier_id, brand or "", model or "", bool(is_active), existing),
                )
                return existing

        row = self.connection.execute(
            """
            INSERT INTO vehicles(plate_number, monitoring_id, carrier_id, brand, model, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(plate_number) DO UPDATE SET
                monitoring_id = COALESCE(excluded.monitoring_id, vehicles.monitoring_id),
                carrier_id = excluded.carrier_id,
                brand = excluded.brand,
                model = excluded.model,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (plate_number, monitoring_id, carrier_id, brand or "", model or "", bool(is_active)),
        ).fetchone()
        return int(row["id"])

    def _upsert_driver(self, *, full_name: str, phone: str, carrier_id: int | None, is_active: bool) -> int | None:
        full_name = str(full_name or "").strip()
        phone = str(phone or "").strip()
        if not full_name and not phone:
            return None

        existing = self._lookup().fetch_id(
            "SELECT id FROM drivers WHERE full_name = %s AND phone = %s",
            (full_name, phone),
        )
        if existing is None:
            row = self.connection.execute(
                """
                INSERT INTO drivers(full_name, phone, carrier_id, is_active)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (full_name, phone, carrier_id, bool(is_active)),
            ).fetchone()
            return int(row["id"])

        self.connection.execute(
            """
            UPDATE drivers
            SET carrier_id = %s, is_active = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (carrier_id, bool(is_active), existing),
        )
        return existing

    def _lookup(self) -> PostgresTaskLookup:
        return PostgresTaskLookup(self.connection, self.source_key)

    def _positive_int_or_none(self, value: Any) -> int | None:
        parsed = self._lookup().to_int_or_none(value)
        if parsed is None or parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _first_planned_time(points: list[Any]) -> str | None:
        if not points:
            return None
        return points[0].planned_datetime_text() or None

    @staticmethod
    def _last_planned_time(points: list[Any]) -> str | None:
        if not points:
            return None
        return points[-1].planned_datetime_text() or None

    @staticmethod
    def _status_from_row(row: dict[str, Any]) -> str:
        status = str(row.get("status") or "").strip()
        return status or "active"
