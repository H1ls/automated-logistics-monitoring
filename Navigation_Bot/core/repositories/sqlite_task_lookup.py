from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

"""
Поиск и вычисление ключей рейса.
Этот класс хранит правила, как связать старую строку Google с внутренним рейсом:
    google_sheet_row показывает, куда писать обратно в Google, а trip_number является внутренним номером рейса в нашей БД. 
    Вся логика подбора этих ключей должна жить здесь, а не расползаться по writer/reader.
"""


@dataclass(slots=True)
class SqliteTaskLookup:
    """Небольшой помощник для поиска id и вычисления trip_number."""

    connection: sqlite3.Connection
    source_key: str = ""

    def resolve_trip_number(self, row: dict[str, Any], google_sheet_row: int | None) -> int:
        """Находит существующий trip_number или выдает следующий свободный."""
        # Если строка уже содержит внутренний номер, доверяем ему.
        explicit = self.to_int_or_none(row.get("trip_number")) or self.to_int_or_none(row.get("task_index"))
        if explicit is not None:
            return explicit

        # db_task_id самый надежный способ найти уже сохраненный рейс.
        db_task_id = self.to_int_or_none(row.get("db_task_id"))
        if db_task_id is not None:
            found = self.fetch_id("SELECT trip_number FROM tasks WHERE id = ?", (db_task_id,))
            if found is not None:
                return found

        if google_sheet_row is not None:
            if self.source_key:
                # В разных листах Google может быть одинаковый номер строки, поэтому учитываем source_key.
                found = self.fetch_id(
                    """
                    SELECT trip_number FROM tasks
                    WHERE google_sheet_row = ? AND google_worksheet_title = ?
                    """,
                    (google_sheet_row, self.source_key),
                )
                if found is not None:
                    return found
                return self.next_trip_number()

            found = self.fetch_id(
                "SELECT trip_number FROM tasks WHERE google_sheet_row = ?",
                (google_sheet_row,),
            )
            if found is not None:
                return found

        return self.next_trip_number()

    def next_trip_number(self) -> int:
        """Возвращает следующий внутренний номер рейса."""
        value = self.connection.execute("SELECT COALESCE(MAX(trip_number), 0) + 1 FROM tasks").fetchone()[0]
        return int(value or 1)

    def task_id_by_trip_number(self, trip_number: int) -> int | None:
        """Возвращает tasks.id по внутреннему номеру рейса."""
        return self.fetch_id("SELECT id FROM tasks WHERE trip_number = ?", (trip_number,))

    def fetch_id(self, query: str, params: tuple[Any, ...]) -> int | None:
        """Выполняет SELECT одного id/числа и возвращает int или None."""
        row = self.connection.execute(query, params).fetchone()
        if row is None:
            return None
        value = row[0]
        return int(value) if value is not None else None

    @staticmethod
    def to_int_or_none(value: Any) -> int | None:
        """Безопасно приводит значение к int, если это целое число."""
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
