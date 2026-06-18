from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb


class PostgresAuditRepository:
    def __init__(self, connection):
        self.connection = connection

    def record(
        self,
        *,
        user: dict[str, Any],
        entity_type: str,
        action: str,
        entity_id: int | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        source: str = "api",
    ) -> None:
        changed_fields = self._changed_fields(before_data, after_data)
        self.connection.execute(
            """
            INSERT INTO audit_log(
                user_id, username, role, entity_type, entity_id, action,
                before_data, after_data, changed_fields, source
            )
            VALUES (
                %(user_id)s, %(username)s, %(role)s, %(entity_type)s, %(entity_id)s, %(action)s,
                %(before_data)s, %(after_data)s, %(changed_fields)s, %(source)s
            )
            """,
            {
                "user_id": user.get("id"),
                "username": user.get("username") or "",
                "role": user.get("role") or "",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "before_data": Jsonb(self._json_safe(before_data)) if before_data is not None else None,
                "after_data": Jsonb(self._json_safe(after_data)) if after_data is not None else None,
                "changed_fields": Jsonb(self._json_safe(changed_fields)),
                "source": source,
            },
        )

    def record_compact(
        self,
        *,
        user: dict[str, Any],
        entity_type: str,
        action: str,
        entity_id: int | None = None,
        summary: dict[str, Any] | None = None,
        source: str = "api",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO audit_log(
                user_id, username, role, entity_type, entity_id, action,
                changed_fields, source
            )
            VALUES (
                %(user_id)s, %(username)s, %(role)s, %(entity_type)s, %(entity_id)s, %(action)s,
                %(changed_fields)s, %(source)s
            )
            """,
            {
                "user_id": user.get("id"),
                "username": user.get("username") or "",
                "role": user.get("role") or "",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "changed_fields": Jsonb(self._json_safe(summary or {})),
                "source": source,
            },
        )

    def task_snapshot(self, task_id: int | None = None, *, trip_number: int | None = None) -> dict[str, Any] | None:
        if task_id is not None:
            row = self.connection.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        elif trip_number is not None:
            row = self.connection.execute("SELECT * FROM tasks WHERE trip_number = %s", (trip_number,)).fetchone()
        else:
            return None
        return dict(row) if row is not None else None

    def vehicle_snapshot(self, vehicle_id: int | None) -> dict[str, Any] | None:
        if vehicle_id is None:
            return None
        row = self.connection.execute("SELECT * FROM vehicles WHERE id = %s", (vehicle_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_entries(
        self,
        *,
        entity_type: str = "",
        entity_id: int | None = None,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 100), 500))}
        if entity_type:
            conditions.append("entity_type = %(entity_type)s")
            params["entity_type"] = entity_type
        if entity_id is not None:
            conditions.append("entity_id = %(entity_id)s")
            params["entity_id"] = entity_id
        if user_id is not None:
            conditions.append("user_id = %(user_id)s")
            params["user_id"] = user_id

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM audit_log
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT %(limit)s
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    @classmethod
    def _changed_fields(
        cls,
        before_data: dict[str, Any] | None,
        after_data: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        before_data = before_data or {}
        after_data = after_data or {}
        keys = sorted(set(before_data) | set(after_data))
        changed: dict[str, dict[str, Any]] = {}
        for key in keys:
            before_value = cls._json_safe(before_data.get(key))
            after_value = cls._json_safe(after_data.get(key))
            if before_value != after_value:
                changed[key] = {"before": before_value, "after": after_value}
        return changed

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value
