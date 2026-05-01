from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Callable

from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.processed_flags import init_processed_flags
from Navigation_Bot.core.application.mappers.google_row_mapper import GoogleRowMapper
from Navigation_Bot.core.domain.entities.status_event import StatusEvent


@dataclass(slots=True)
class TasksService:
    task_repository: Any
    log: Callable[[str], None] | None = None
    status_event_service: Any | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def get_task(self, real_idx: int) -> Task | None:
        row = self.get_row(real_idx)
        if not row:
            return None

        try:
            return TaskMapper.from_dict(row)
        except Exception as e:
            self._log(f"⚠️ TasksService.get_task: {e}")
            return None

    def save_task_by_index(self, task: Task) -> tuple[bool, Task | None, str | None]:
        if not isinstance(task, Task):
            return False, None, "task_invalid"

        index_key = task.index
        if not index_key:
            return False, None, "missing_index"

        real_idx = self.find_real_idx_by_index_key(index_key)
        if real_idx is None:
            return False, None, "row_not_found"

        task.ensure_processing_consistency()
        return self.save_task(real_idx, task)

    # TODO:  save_task() не пересчитывает processed
    # либо валидировать Task перед сохранением
    # либо нормализовать processed под число выгрузок
    # либо вспомогательный метод _normalize_task_before_save(task)
    # ---
    # Полностью заменяет строку данными из TaskMapper.to_dict(task).
    # Использовать только там, где нужна полная пересборка строки.
    # Пересохранения для highlight_for
    def save_task(self, real_idx: int, task: Task) -> tuple[bool, Task | None, str | None]:
        try:
            data = self.task_repository.get()

            if real_idx < 0 or real_idx >= len(data):
                return False, None, "row_out_of_range"

            task.ensure_processing_consistency()
            task_dict = TaskMapper.to_dict(task)

            old_row = data[real_idx] or {}

            preserved_fields = {k: v for k, v in old_row.items()
                                if k not in task_dict
                                }

            merged = {**task_dict, **preserved_fields}

            data[real_idx] = merged

            self.task_repository.set(data)

            return True, task, None

        except Exception as e:
            self.log(f"❌ TasksService.save_task: {e}")
            return False, None, str(e)

    def _get_data(self) -> tuple[list | None, str | None]:
        data = self.task_repository.get()
        if data is None:
            return None, "task_repository _empty"
        if not isinstance(data, list):
            return None, "task_repository _invalid"
        return data, None

    def get_all(self) -> list[dict]:
        data, err = self._get_data()
        if err:
            return []
        return [row for row in data if isinstance(row, dict)]

    def get_row(self, real_idx: int) -> dict | None:
        data, err = self._get_data()
        if err:
            return None
        if not (0 <= real_idx < len(data)):
            return None
        row = data[real_idx]
        return row if isinstance(row, dict) else None

    def find_real_idx_by_index_key(self, index_key: int) -> int | None:
        data, err = self._get_data()
        if err:
            return None
        for i, row in enumerate(data):
            if isinstance(row, dict) and row.get("index") == index_key:
                return i
        return None

    def delete_row(self, real_idx: int) -> tuple[bool, dict | None, str | None]:
        data, err = self._get_data()
        if err:
            return False, None, err
        if not (0 <= real_idx < len(data)):
            return False, None, "row_out_of_range"

        row = data[real_idx]
        if not isinstance(row, dict):
            return False, None, "row_not_dict"

        removed = data.pop(real_idx)
        self.task_repository.save()
        return True, removed, None

    def apply_patch(self, real_idx: int, patch: dict) -> tuple[bool, dict | None, str | None]:
        data, err = self._get_data()
        if err:
            return False, None, err
        if not (0 <= real_idx < len(data)):
            return False, None, "row_out_of_range"

        row = data[real_idx]
        if not isinstance(row, dict):
            return False, None, "row_not_dict"
        if not isinstance(patch, dict) or not patch:
            return False, None, "empty_patch"

        changed = False
        for key, value in patch.items():
            if row.get(key) != value:
                row[key] = value
                changed = True

        if "Выгрузка" in patch or "Погрузка" in patch:
            init_processed_flags(data, data, loads_key="Выгрузка")
            changed = True

        if changed:
            self.task_repository.save()

        return True, row, None

    def update_editable_field(self, real_idx: int, header: str, value: str) -> tuple[bool, dict | None, str | None]:
        allowed = {"Телефон", "ФИО", "КА", "id"}
        if header not in allowed:
            return False, None, "field_not_allowed"

        if header == "id":
            value_str = str(value).strip()
            if not value_str:
                return False, None, "empty_id"
            if not value_str.isdigit():
                return False, None, "invalid_id"
            normalized_value = int(value_str)
        else:
            normalized_value = str(value)

        return self.apply_patch(real_idx, {header: normalized_value})

    def add_task(self, task: dict) -> tuple[bool, dict | None, str | None]:
        data, err = self._get_data()
        if err:
            return False, None, err
        if not isinstance(task, dict):
            return False, None, "task_invalid"

        last_index = max([row.get("index", 0) for row in data if isinstance(row, dict)], default=0, )

        new_task = dict(task)
        new_task["index"] = last_index + 1

        data.append(new_task)
        init_processed_flags(data, data, loads_key="Выгрузка")
        self.task_repository.save()

        return True, new_task, None

    # TODO:В перспективе вынести либо в:GoogleSyncService, отдельный mapper типа GoogleRowMapper
    def build_row_from_google_dh(self, index_key: int, dh: list[str]) -> dict:
        return GoogleRowMapper.build_row(index_key, dh)

    def add_only_missing_rows_from_google(self, rows_map: dict[int, list[str]]) -> tuple[bool, dict | None, str | None]:
        """
        Добавляет только новые строки из Google.
        Существующие по index НЕ изменяет.
        Ничего не удаляет.

        Возвращает:
            (ok, stats, err)
        где stats = {"added": int, "skipped_existing": int}
        """
        data, err = self._get_data()
        if err:
            return False, None, err

        if not isinstance(rows_map, dict):
            return False, None, "rows_map_invalid"

        existing_indexes = {row.get("index")
                            for row in data
                            if isinstance(row, dict) and row.get("index") is not None
                            }

        added_count = 0
        skipped_existing = 0

        for index_key, dh in rows_map.items():
            if not isinstance(index_key, int):
                continue
            if not isinstance(dh, list):
                continue

            if index_key in existing_indexes:
                skipped_existing += 1
                continue

            fresh = self.build_row_from_google_dh(index_key, dh)

            # защита от полностью пустой строки
            if not any([fresh.get("ТС"),
                        fresh.get("Телефон"),
                        fresh.get("ФИО"),
                        fresh.get("КА"),
                        fresh.get("Погрузка"),
                        fresh.get("Выгрузка"), ]):
                continue

            data.append(fresh)
            existing_indexes.add(index_key)
            added_count += 1

        init_processed_flags(data, data, loads_key="Выгрузка")
        self.task_repository.save()

        return (True, {"added": added_count,
                       "skipped_existing": skipped_existing, },
                None)

    def remove_completed_tasks(self, active_google_indexes: set[int]) -> tuple[bool, dict | None, str | None]:
        """
        Удаляет из локального task_repository строки, которых больше нет среди активных строк Google.
        То есть задачи, которые в Google стали "Готов" или исчезли из активной выборки.

        Возвращает:
            (ok, stats, err)
        где stats = {"deleted": int}
        """
        data, err = self._get_data()
        if err:
            return False, None, err

        if not isinstance(active_google_indexes, set):
            return False, None, "active_google_indexes_invalid"

        original_len = len(data)

        filtered = []
        for row in data:
            if not isinstance(row, dict):
                continue

            index_key = row.get("index")
            if index_key in active_google_indexes:
                filtered.append(row)

        deleted_count = original_len - len(filtered)

        if deleted_count > 0:
            self.task_repository.set(filtered)

        return True, {"deleted": deleted_count}, None

    def mark_unload_processed(self, index_key: int, unload_idx: int) -> tuple[bool, Task | None, str | None]:
        self._log(f"🧪 mark_unload_processed вызван: index={index_key}, unload_idx={unload_idx}")
        real_idx = self.find_real_idx_by_index_key(index_key)
        if real_idx is None:
            return False, None, "row_not_found"

        task = self.get_task(real_idx)
        if task is None:
            return False, None, "task_not_found"

        unloads_count = len(task.route_plan.unloads)
        if unload_idx < 0:
            return False, None, "invalid_unload_idx"
        if unload_idx >= unloads_count:
            return False, None, "unload_idx_out_of_range"

        # сохрани старое состояние ДО изменения
        old_processed = list(task.processing.processed_unloads)

        # изменение
        task.mark_unload_processed(unload_idx)

        # сохранить
        ok, saved_task, err = self.save_task(real_idx, task)
        if not ok:
            return False, None, err

        # новое состояние ПОСЛЕ
        new_processed = list(task.processing.processed_unloads)

        # записать событие
        # TODO: Временно не используется, вернутся после FastApi, для отслеживания действия Users
        self._save_status_event(task_index=index_key,
                                event_type="unload_done",
                                field_name=f"processed[{unload_idx}]",
                                old_value=str(old_processed),
                                new_value=str(new_processed),
                                message=f"Выгрузка #{unload_idx + 1} отмечена обработанной",
                                source="maps", )
        return True, saved_task, None

    def exists_row(self, real_idx: int) -> bool:
        data, err = self._get_data()
        if err:
            return False
        return 0 <= real_idx < len(data) and isinstance(data[real_idx], dict)

    def get_processible_rows(self) -> list[tuple[int, int | None]]:
        data, err = self._get_data()
        if err:
            return []

        result: list[tuple[int, int | None]] = []

        for row_idx, row in enumerate(data):
            if not isinstance(row, dict):
                continue
            if not row.get("id") or not row.get("ТС"):
                continue
            result.append((row_idx, row.get("index")))

        return result

    def get_index_key_by_row(self, real_idx: int) -> int | None:
        row = self.get_row(real_idx)
        if not row:
            return None
        return row.get("index")

    # TODO: Временно на паузе
    def _save_status_event(self,
                           *,
                           task_index: int,
                           event_type: str,
                           field_name: str = "",
                           old_value: str = "",
                           new_value: str = "",
                           message: str = "",
                           source: str = "system", ) -> None:
        self._log(f"🧪 _save_status_event вызван: {event_type}, task_index={task_index}")
        if not self.status_event_service:
            self._log("⚠️ status_event_service не подключён")
            return

        try:
            event = StatusEvent(task_index=task_index,
                                event_type=event_type,
                                field_name=field_name,
                                old_value=str(old_value or ""),
                                new_value=str(new_value or ""),
                                message=message,
                                source=source, )
            self._log(f"📝 StatusEvent сохранён: {event_type} / {message}")
            self.status_event_service.append(event)
        except Exception as e:
            self._log(f"⚠️ Не удалось сохранить StatusEvent: {e}")
