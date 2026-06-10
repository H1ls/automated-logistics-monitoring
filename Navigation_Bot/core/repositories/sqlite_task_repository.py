from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.repositories.sqlite_task_reader import SqliteTaskReader
from Navigation_Bot.core.repositories.sqlite_task_writer import SqliteTaskWriter


"""
Фасад над SQLite-хранилищем рейсов.

Этот класс оставляет старый API репозитория, которым пользуются GUI и сервисы,
но сам почти не работает с SQL. Чтение, запись, lookup и точки маршрута вынесены
в отдельные классы. Если здесь снова начнет появляться много SQL, значит логику
лучше вынести в reader/writer/lookup.
"""


@dataclass(slots=True)
class SqliteTaskRepository:
    """Совместимый со старым JSON-репозиторием фасад с in-memory кэшем строк."""

    connection: sqlite3.Connection
    log: Callable[[str], None] | None = None
    data: list[dict] | None = None
    current_source_key: str = ""

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    # --- Старый API, который уже используют GUI и сервисы ---

    def set_source_key(self, source_key: str) -> None:
        """Переключает активный лист Google и перечитывает видимые рейсы."""
        self.current_source_key = str(source_key or "default")
        self.reload()

    def reload(self) -> None:
        """Обновляет кэш legacy-строк из нормализованной SQLite-БД."""
        self.data = SqliteTaskReader(self.connection).load_active_rows(self.current_source_key)

    def save(self, *, source: str = "user") -> None:
        """Сохраняет текущий кэш обратно в SQLite."""
        self.sync_rows(self.get(), source=source)

    def get(self) -> list[dict]:
        """Возвращает кэш legacy-строк, при первом обращении читает их из БД."""
        if self.data is None:
            self.reload()
        return self.data if self.data is not None else []

    def set(self, new_data: list, *, source: str = "user") -> None:
        """Заменяет активный набор строк и завершает рейсы, которых больше нет в наборе."""
        rows = [row for row in new_data if isinstance(row, dict)]
        self.sync_rows(rows, source=source)
        self._writer().mark_missing_rows_inactive(rows)
        self.data = rows

    def append(self, entry: dict, *, source: str = "user") -> None:
        """Добавляет одну legacy-строку в кэш и SQLite."""
        data = self.get()
        data.append(entry)
        self.upsert_from_row(entry, source=source)

    def list_tasks(self) -> list[Task]:
        """Возвращает кэшированные строки как доменные объекты Task."""
        return [TaskMapper.from_dict(row) for row in self.get() if isinstance(row, dict)]

    def get_by_index(self, index_key: int) -> Task | None:
        """Ищет рейс по legacy index; сейчас это строка Google Sheets."""
        for row in self.get():
            if isinstance(row, dict) and row.get("index") == index_key:
                return TaskMapper.from_dict(row)
        return None

    def save_task(self, task: Task, *, source: str = "user") -> None:
        """Сохраняет Task, сохраняя поля старого dict, которых нет в доменной модели."""
        task.ensure_processing_consistency()
        task_dict = TaskMapper.to_dict(task)
        index_key = task.index
        data = self.get()

        for i, row in enumerate(data):
            if isinstance(row, dict) and row.get("index") == index_key:
                merged = {**task_dict, **{k: v for k, v in row.items() if k not in task_dict}}
                data[i] = merged
                self.upsert_from_row(merged, source=source)
                return

        data.append(task_dict)
        self.upsert_from_row(task_dict, source=source)

    def replace_all(self, tasks: list[Task], *, source: str = "user") -> None:
        """Полностью заменяет активные строки набором доменных Task."""
        rows = []
        for task in tasks:
            task.ensure_processing_consistency()
            rows.append(TaskMapper.to_dict(task))
        self.set(rows, source=source)

    def delete_by_index(self, index_key: int) -> bool:
        """Помечает один рейс завершенным по legacy index."""
        data = self.get()
        for i, row in enumerate(data):
            if isinstance(row, dict) and row.get("index") == index_key:
                data.pop(i)
                self._writer().mark_index_inactive(index_key)
                return True
        return False

    def complete_row(self, real_idx: int, *, source: str = "user") -> tuple[bool, dict | None, str | None]:
        """Marks a visible row as completed and removes it from the active in-memory list."""
        data = self.get()
        if not (0 <= real_idx < len(data)):
            return False, None, "row_out_of_range"

        row = data[real_idx]
        if not isinstance(row, dict):
            return False, None, "row_not_dict"

        row_identity = row.get("trip_number") or row.get("google_sheet_row") or row.get("index")
        if row_identity is None:
            return False, None, "missing_row_identity"

        if not self._writer().mark_task_completed(row_identity, source=source):
            return False, None, "task_not_found"

        removed = data.pop(real_idx)
        return True, removed, None

    def sync_rows(self, rows: list[dict], *, source: str = "user") -> None:
        """Синхронизирует список legacy-строк с нормализованными таблицами SQLite."""
        for row in rows:
            if isinstance(row, dict):
                self.upsert_from_row(row, source=source)

    def upsert_from_row(self, row: dict[str, Any], *, source: str = "user") -> dict[str, int] | None:
        """Делегирует сохранение одной строки writer-классу."""
        return self._writer().upsert_from_row(row, source=source)

    def _writer(self) -> SqliteTaskWriter:
        """Создает writer, привязанный к текущему листу Google."""
        return SqliteTaskWriter(self.connection, self.current_source_key)
