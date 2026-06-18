from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PostgresTaskLookup:
    connection: Any
    source_key: str = ""

    def resolve_trip_number(self, row: dict[str, Any], google_sheet_row: int | None) -> int:
        explicit = self.to_int_or_none(row.get("trip_number"))
        if explicit is not None:
            return explicit

        db_task_id = self.to_int_or_none(row.get("db_task_id"))
        if db_task_id is not None:
            found = self.fetch_id("SELECT trip_number FROM tasks WHERE id = %s", (db_task_id,))
            if found is not None:
                return found

        if google_sheet_row is not None:
            if self.source_key:
                found = self.fetch_id(
                    """
                    SELECT trip_number FROM tasks
                    WHERE google_sheet_row = %s AND google_worksheet_title = %s
                    """,
                    (google_sheet_row, self.source_key),
                )
                if found is not None:
                    return found
                return self.next_trip_number()

            found = self.fetch_id(
                "SELECT trip_number FROM tasks WHERE google_sheet_row = %s",
                (google_sheet_row,),
            )
            if found is not None:
                return found

        return self.next_trip_number()

    def next_trip_number(self) -> int:
        row = self.connection.execute("SELECT COALESCE(MAX(trip_number), 0) + 1 AS value FROM tasks").fetchone()
        return int(row["value"] or 1)

    def task_id_by_trip_number(self, trip_number: int) -> int | None:
        return self.fetch_id("SELECT id FROM tasks WHERE trip_number = %s", (trip_number,))

    def fetch_id(self, query: str, params: tuple[Any, ...]) -> int | None:
        row = self.connection.execute(query, params).fetchone()
        if row is None:
            return None
        value = next(iter(row.values())) if isinstance(row, dict) else row[0]
        return int(value) if value is not None else None

    @staticmethod
    def to_int_or_none(value: Any) -> int | None:
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
