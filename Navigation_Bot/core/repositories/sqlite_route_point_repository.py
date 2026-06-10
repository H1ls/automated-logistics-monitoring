from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from Navigation_Bot.core.repositories.sqlite_status_event_repository import SqliteStatusEventRepository

"""
Синхронизация точек маршрута.
route_points хранят погрузки и выгрузки рейса в нормализованном виде. Обновляет точки стабильно по паре 
(task_id, point_type, sequence): если адрес или время изменились, обновляется та же запись route_points.id, 
а изменение фиксируется в status_events.
"""


@dataclass(slots=True)
class SqliteRoutePointRepository:
    """Отвечает за создание/обновление/удаление route_points и события по ним."""

    connection: sqlite3.Connection

    def sync_route_points(
            self,
            task_id: int,
            point_type: str,
            points: list[Any],
            processed_unloads: list[bool],
            source: str,
    ) -> None:
        """Синхронизирует точки одного типа: load или unload."""
        existing = self._existing_route_points(task_id, point_type)
        seen_sequences: set[int] = set()

        for point in points:
            sequence = int(point.sequence)
            seen_sequences.add(sequence)
            is_processed = 0
            if point.kind == "unload":
                unload_idx = max(sequence - 1, 0)
                if unload_idx < len(processed_unloads):
                    is_processed = int(bool(processed_unloads[unload_idx]))

            old = existing.get(sequence)
            new_values = {
                "location": point.address or "",
                "scheduled_time": point.planned_datetime_text() or "",
                "comment": point.comment or "",
                "is_processed": is_processed,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "geocoding_source": point.geocoding_source or ("parsed" if point.latitude is not None and point.longitude is not None else ""),
            }

            if old is None:
                # Новой sequence еще нет в БД - создаем точку и пишем событие создания.
                cursor = self.connection.execute(
                    """
                    INSERT INTO route_points (
                        task_id, sequence, point_type, location, scheduled_time,
                        comment, is_processed, latitude, longitude, geocoding_source, geocoded_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? IS NOT NULL AND ? IS NOT NULL THEN CURRENT_TIMESTAMP ELSE NULL END)
                    """,
                    (
                        task_id,
                        sequence,
                        point.kind,
                        new_values["location"],
                        new_values["scheduled_time"],
                        new_values["comment"],
                        new_values["is_processed"],
                        new_values["latitude"],
                        new_values["longitude"],
                        new_values["geocoding_source"],
                        new_values["latitude"],
                        new_values["longitude"],
                    ),
                )
                self._insert_status_event(
                    task_id=task_id,
                    route_point_id=int(cursor.lastrowid),
                    event_type="route_point_created",
                    field_name=f"{point_type}[{sequence}]",
                    old_value="",
                    new_value=self._route_point_event_value(new_values),
                    message=f"{point_type} point #{sequence} created",
                    source=source,
                )
                continue

            changed_fields = {
                field: (old[field], new_value)
                for field, new_value in new_values.items()
                if old[field] != new_value
            }
            if not changed_fields:
                continue

            # Точка уже есть - обновляем ту же строку, не создавая новый route_points.id.
            self.connection.execute(
                """
                UPDATE route_points
                SET location = ?,
                    scheduled_time = ?,
                    comment = ?,
                    is_processed = ?,
                    latitude = ?,
                    longitude = ?,
                    geocoding_source = ?,
                    geocoded_at = CASE
                        WHEN ? IS NOT NULL AND ? IS NOT NULL
                             AND (latitude IS NOT ? OR longitude IS NOT ?)
                        THEN CURRENT_TIMESTAMP
                        ELSE geocoded_at
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    new_values["location"],
                    new_values["scheduled_time"],
                    new_values["comment"],
                    new_values["is_processed"],
                    new_values["latitude"],
                    new_values["longitude"],
                    new_values["geocoding_source"],
                    new_values["latitude"],
                    new_values["longitude"],
                    new_values["latitude"],
                    new_values["longitude"],
                    old["id"],
                ),
            )

            for field, (old_value, new_value) in changed_fields.items():
                self._insert_status_event(
                    task_id=task_id,
                    route_point_id=old["id"],
                    event_type="route_point_updated",
                    field_name=f"{point_type}[{sequence}].{field}",
                    old_value=str(old_value if old_value is not None else ""),
                    new_value=str(new_value if new_value is not None else ""),
                    message=f"{point_type} point #{sequence} {field} changed",
                    source=source,
                )

        for sequence, old in existing.items():
            if sequence in seen_sequences:
                continue
            # Sequence исчезла из входных данных - фиксируем удаление и удаляем точку.
            self._insert_status_event(
                task_id=task_id,
                route_point_id=old["id"],
                event_type="route_point_deleted",
                field_name=f"{point_type}[{sequence}]",
                old_value=self._route_point_event_value(old),
                new_value="",
                message=f"{point_type} point #{sequence} deleted",
                source=source,
            )
            self.connection.execute("DELETE FROM route_points WHERE id = ?", (old["id"],))

    def _existing_route_points(self, task_id: int, point_type: str) -> dict[int, dict]:
        """Возвращает существующие точки по sequence, чтобы обновлять их стабильно."""
        rows = self.connection.execute(
            """
            SELECT id, sequence, location, scheduled_time, comment, is_processed,
                   latitude, longitude, geocoding_source
            FROM route_points
            WHERE task_id = ? AND point_type = ?
            """,
            (task_id, point_type),
        ).fetchall()
        return {
            int(row["sequence"]): {
                "id": int(row["id"]),
                "location": row["location"] or "",
                "scheduled_time": row["scheduled_time"] or "",
                "comment": row["comment"] or "",
                "is_processed": int(row["is_processed"] or 0),
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "geocoding_source": row["geocoding_source"] or "",
            }
            for row in rows
        }

    def _insert_status_event(
            self,
            *,
            task_id: int,
            route_point_id: int | None,
            event_type: str,
            field_name: str,
            old_value: str,
            new_value: str,
            message: str,
            source: str,
    ) -> None:
        """Пишет событие изменения точки маршрута в status_events."""
        SqliteStatusEventRepository(self.connection).append_route_point_event(
            task_id=task_id,
            route_point_id=route_point_id,
            event_type=event_type,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            message=message,
            source=source,
        )

    @staticmethod
    def _route_point_event_value(row: dict) -> str:
        """Собирает компактное текстовое значение точки для old_value/new_value."""
        return (
            f"location={row.get('location', '')}; "
            f"scheduled_time={row.get('scheduled_time', '')}; "
            f"comment={row.get('comment', '')}; "
            f"is_processed={row.get('is_processed', 0)}; "
            f"latitude={row.get('latitude', '')}; "
            f"longitude={row.get('longitude', '')}; "
            f"geocoding_source={row.get('geocoding_source', '')}"
        )
