from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

ALLOWED_EVENT_SOURCES = {"user", "google", "google_replaced", "cleaner", "maps", "manual"}


@dataclass(slots=True)
class SqliteStatusEventRepository:
    """Хелпер для единой записи событий "status_events"""

    connection: sqlite3.Connection

    def append_task_event(
            self,
            *,
            task_id: int,
            event_type: str,
            field_name: str = "",
            old_value: Any = "",
            new_value: Any = "",
            message: str = "",
            source: str = "user",
            route_point_id: int | None = None,
    ) -> int:
        normalized_source = source if source in ALLOWED_EVENT_SOURCES else "user"
        cursor = self.connection.execute(
            """
            INSERT INTO status_events (
                task_id, route_point_id, event_type, field_name,
                old_value, new_value, message, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                route_point_id,
                event_type,
                field_name,
                self._text(old_value),
                self._text(new_value),
                message or "",
                normalized_source,
            ),
        )
        return int(cursor.lastrowid)

    def append_field_change(
            self,
            *,
            task_id: int,
            field_name: str,
            old_value: Any,
            new_value: Any,
            source: str = "user",
            event_type: str = "task_field_updated",
            message: str = "",
    ) -> int | None:
        old_text = self._text(old_value)
        new_text = self._text(new_value)
        if old_text == new_text:
            return None

        return self.append_task_event(
            task_id=task_id,
            event_type=event_type,
            field_name=field_name,
            old_value=old_text,
            new_value=new_text,
            message=message or f"{field_name} changed",
            source=source,
        )

    def append_route_point_event(
            self,
            *,
            task_id: int,
            route_point_id: int | None,
            event_type: str,
            field_name: str,
            old_value: Any = "",
            new_value: Any = "",
            message: str = "",
            source: str = "user",
    ) -> int:
        return self.append_task_event(
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
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)
