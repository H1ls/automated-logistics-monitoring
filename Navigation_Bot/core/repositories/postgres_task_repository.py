from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.repositories.postgres_task_reader import PostgresTaskReader
from Navigation_Bot.core.repositories.postgres_task_writer import PostgresTaskWriter


@dataclass(slots=True)
class PostgresTaskRepository:
    connection: Any
    log: Callable[[str], None] | None = None
    data: list[dict] | None = None
    current_source_key: str = ""

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def set_source_key(self, source_key: str, *, reload: bool = True) -> None:
        self.current_source_key = str(source_key or "")
        if reload:
            self.reload()

    def reload(self) -> None:
        self.data = PostgresTaskReader(self.connection).load_active_rows(self.current_source_key)

    def get(self) -> list[dict]:
        if self.data is None:
            self.reload()
        return self.data if self.data is not None else []

    def list_tasks(self) -> list[Task]:
        return [TaskMapper.from_dict(row) for row in self.get() if isinstance(row, dict)]

    def get_by_index(self, index_key: int) -> Task | None:
        for row in self.get():
            if isinstance(row, dict) and row.get("index") == index_key:
                return TaskMapper.from_dict(row)
        return None

    def save(self, *, source: str = "user") -> None:
        self.sync_rows(self.get(), source=source)

    def set(self, new_data: list, *, source: str = "user") -> None:
        rows = [row for row in new_data if isinstance(row, dict)]
        self.sync_rows(rows, source=source)
        self.data = rows

    def append(self, entry: dict, *, source: str = "user") -> None:
        data = self.get()
        data.append(entry)
        self.upsert_from_row(entry, source=source)

    def save_task(self, task: Task, *, source: str = "user") -> None:
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
        rows = []
        for task in tasks:
            task.ensure_processing_consistency()
            rows.append(TaskMapper.to_dict(task))
        self.set(rows, source=source)

    def delete_by_index(self, index_key: int) -> bool:
        data = self.get()
        for i, row in enumerate(data):
            if isinstance(row, dict) and row.get("index") == index_key:
                data.pop(i)
                self._writer().mark_index_inactive(index_key)
                return True
        return False

    def complete_row(self, real_idx: int, *, source: str = "user") -> tuple[bool, dict | None, str | None]:
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
        for row in rows:
            if isinstance(row, dict):
                self.upsert_from_row(row, source=source)

    def upsert_from_row(self, row: dict[str, Any], *, source: str = "user") -> dict[str, Any] | None:
        return self._writer().upsert_from_row(row, source=source)

    @staticmethod
    def _write_not_supported() -> None:
        raise NotImplementedError("PostgreSQL task writes are not implemented yet.")

    def _writer(self) -> PostgresTaskWriter:
        return PostgresTaskWriter(self.connection, self.current_source_key)
