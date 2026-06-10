from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.processed_flags import init_processed_flags
from Navigation_Bot.core.application.mappers.google_row_mapper import GoogleRowMapper
from Navigation_Bot.core.domain.entities.status_event import StatusEvent
from Navigation_Bot.core.task_identity import google_sheet_row, row_identity_for_gui, trip_number

AUDITED_USER_FIELDS = {"id", "Телефон", "ФИО", "КА", "status"}


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

        google_row = task.index
        if not google_row:
            return False, None, "missing_index"

        real_idx = self.find_real_idx_by_google_sheet_row(google_row)
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

            self.task_repository.set(data, source="user")

            return True, task, None

        except Exception as e:
            self._log(f"❌ TasksService.save_task: {e}")
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
        if err or data is None:
            return []
        return [row for row in data if isinstance(row, dict)]

    def get_row(self, real_idx: int) -> dict | None:
        data, err = self._get_data()
        if err or data is None:
            return None
        if not (0 <= real_idx < len(data)):
            return None
        row = data[real_idx]
        return row if isinstance(row, dict) else None

    def find_real_idx_by_index_key(self, index_key: int) -> int | None:
        """Legacy-lookup по ключу GUI; сейчас это google_sheet_row/index."""
        return self.find_real_idx_by_google_sheet_row(index_key)

    def find_real_idx_by_google_sheet_row(self, google_row: int) -> int | None:
        """Ищет реальный индекс строки по номеру строки Google Sheets."""
        data, err = self._get_data()
        if err or data is None:
            return None
        for i, row in enumerate(data):
            if isinstance(row, dict) and google_sheet_row(row) == google_row:
                return i
        return None

    def find_real_idx_by_trip_number(self, task_trip_number: int) -> int | None:
        data, err = self._get_data()
        if err or data is None:
            return None
        for i, row in enumerate(data):
            if isinstance(row, dict) and trip_number(row) == task_trip_number:
                return i
        return None

    def delete_row(self, real_idx: int) -> tuple[bool, dict | None, str | None]:
        return self.complete_row(real_idx, source="user")

    def complete_row(self, real_idx: int, *, source: str = "user") -> tuple[bool, dict | None, str | None]:
        data, err = self._get_data()
        if err or data is None:
            return False, None, err
        if not (0 <= real_idx < len(data)):
            return False, None, "row_out_of_range"

        row = data[real_idx]
        if not isinstance(row, dict):
            return False, None, "row_not_dict"

        task_trip_number = trip_number(row)
        old_status = str(row.get("status") or "active")

        if hasattr(self.task_repository, "complete_row"):
            ok, removed, complete_err = self.task_repository.complete_row(real_idx, source=source)
        else:
            removed = data.pop(real_idx)
            self.task_repository.save(source=source)
            ok, complete_err = True, None

        if not ok:
            return False, None, complete_err

        if task_trip_number:
            self._save_status_event(task_index=task_trip_number,
                                    event_type="task_completed",
                                    field_name="status",
                                    old_value=old_status,
                                    new_value="completed",
                                    message="Рейс завершён вручную" if source == "user" else "Рейс завершён",
                                    source=source, )

        return True, removed, None

    def apply_patch(self, real_idx: int, patch: dict, *, source: str = "user") -> tuple[bool, dict | None, str | None]:
        data, err = self._get_data()
        if err or data is None:
            return False, None, err
        if not (0 <= real_idx < len(data)):
            return False, None, "row_out_of_range"

        row = data[real_idx]
        if not isinstance(row, dict):
            return False, None, "row_not_dict"
        if not isinstance(patch, dict) or not patch:
            return False, None, "empty_patch"

        if source == "google" and self._looks_like_reused_google_row(row, patch):
            row.clear()
            row.update(patch)
            init_processed_flags(data, data, loads_key="Выгрузка")
            self.task_repository.save(source=source)
            return True, row, None

        old_row = dict(row)
        changed = False
        for key, value in patch.items():
            if row.get(key) != value:
                row[key] = value
                changed = True

        if "Выгрузка" in patch or "Погрузка" in patch:
            init_processed_flags(data, data, loads_key="Выгрузка")
            changed = True

        if changed:
            self.task_repository.save(source=source)
            self._save_patch_status_events(old_row, row, patch, source)

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
        if err or data is None:
            return False, None, err
        if not isinstance(task, dict):
            return False, None, "task_invalid"

        new_task = dict(task)
        new_task.pop("index", None)
        new_task.pop("google_sheet_row", None)

        data.append(new_task)
        init_processed_flags(data, data, loads_key="Выгрузка")
        self.task_repository.save(source="user")

        return True, new_task, None

    # TODO:В перспективе вынести либо в:GoogleSyncService, отдельный mapper типа GoogleRowMapper
    def build_row_from_google_dh(self, google_sheet_row_value: int, dh: list[str]) -> dict:
        return GoogleRowMapper.build_row(google_sheet_row_value, dh)

    def add_only_missing_rows_from_google(self, rows_map: dict[int, list[str]]) -> tuple[bool, dict | None, str | None]:
        """
        Добавляет только новые строки из Google.
        Существующие по index НЕ изменяет.
        Ничего не удаляет.

        Возвращает:
            (ok, stats, err)
        где stats = {"added": int, "updated": int, "replaced": int}
        """
        data, err = self._get_data()
        if err or data is None:
            return False, None, err

        if not isinstance(rows_map, dict):
            return False, None, "rows_map_invalid"

        existing_google_rows = {google_sheet_row(row): i
                                for i, row in enumerate(data)
                                if isinstance(row, dict) and google_sheet_row(row) is not None
                                }

        added_count = 0
        updated_count = 0
        replaced_count = 0

        for google_sheet_row_value, dh in rows_map.items():
            if not isinstance(google_sheet_row_value, int):
                continue
            if not isinstance(dh, list):
                continue

            fresh = self.build_row_from_google_dh(google_sheet_row_value, dh)

            # защита от полностью пустой строки
            if not any([fresh.get("ТС"),
                        fresh.get("Телефон"),
                        fresh.get("ФИО"),
                        fresh.get("КА"),
                        fresh.get("Погрузка"),
                        fresh.get("Выгрузка"), ]):
                continue

            existing_idx = existing_google_rows.get(google_sheet_row_value)
            if existing_idx is None:
                data.append(fresh)
                existing_google_rows[google_sheet_row_value] = len(data) - 1
                added_count += 1
                continue

            old_row = data[existing_idx] if 0 <= existing_idx < len(data) else {}
            if isinstance(old_row, dict) and self._looks_like_reused_google_row(old_row, fresh):
                data[existing_idx] = fresh
                replaced_count += 1
            elif isinstance(old_row, dict):
                data[existing_idx] = {**old_row, **fresh}
                updated_count += 1

        init_processed_flags(data, data, loads_key="Выгрузка")
        self.task_repository.save(source="google")

        return (True, {"added": added_count,
                       "updated": updated_count,
                       "replaced": replaced_count, },
                None)

    @staticmethod
    def _looks_like_reused_google_row(old_row: dict, fresh_row: dict) -> bool:
        old_plate = TasksService._signature_text(old_row.get("ТС"))
        new_plate = TasksService._signature_text(fresh_row.get("ТС"))
        old_load = TasksService._signature_text(old_row.get("raw_load") or old_row.get("Погрузка"))
        new_load = TasksService._signature_text(fresh_row.get("raw_load") or fresh_row.get("Погрузка"))
        old_unload = TasksService._signature_text(old_row.get("raw_unload") or old_row.get("Выгрузка"))
        new_unload = TasksService._signature_text(fresh_row.get("raw_unload") or fresh_row.get("Выгрузка"))
        if not old_plate or not new_plate:
            return False
        return old_plate != new_plate and (old_load != new_load or old_unload != new_unload)

    @staticmethod
    def _signature_text(value: Any) -> str:
        return " ".join(str(value or "").lower().split())

    def _save_patch_status_events(self, old_row: dict, new_row: dict, patch: dict, source: str) -> None:
        if source != "user":
            return

        task_trip_number = trip_number(new_row) or trip_number(old_row)
        if not task_trip_number:
            return

        for field_name in patch:
            if field_name not in AUDITED_USER_FIELDS:
                continue
            old_value = old_row.get(field_name)
            new_value = new_row.get(field_name)
            if str(old_value or "") == str(new_value or ""):
                continue

            self._save_status_event(
                task_index=task_trip_number,
                event_type="task_field_updated",
                field_name=field_name,
                old_value=str(old_value or ""),
                new_value=str(new_value or ""),
                message=f"{field_name} changed manually",
                source=source,
            )

    def remove_completed_tasks(self, active_google_indexes: set[int]) -> tuple[bool, dict | None, str | None]:
        """
        Удаляет из локального task_repository строки, которых больше нет среди активных строк Google.
        То есть задачи, которые в Google стали "Готов" или исчезли из активной выборки.

        Возвращает:
            (ok, stats, err)
        где stats = {"deleted": int}
        """
        data, err = self._get_data()
        if err or data is None:
            return False, None, err

        if not isinstance(active_google_indexes, set):
            return False, None, "active_google_indexes_invalid"

        original_len = len(data)

        filtered = []
        for row in data:
            if not isinstance(row, dict):
                continue

            row_google_sheet_row = google_sheet_row(row)
            if row_google_sheet_row in active_google_indexes:
                filtered.append(row)

        deleted_count = original_len - len(filtered)

        if deleted_count > 0:
            self.task_repository.set(filtered, source="google")

        return True, {"deleted": deleted_count}, None

    def mark_unload_processed(self, google_sheet_row_value: int, unload_idx: int) -> tuple[bool, Task | None, str | None]:
        self._log(f"🧪 mark_unload_processed вызван: google_sheet_row={google_sheet_row_value}, unload_idx={unload_idx}")
        real_idx = self.find_real_idx_by_google_sheet_row(google_sheet_row_value)
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
        saved_row = self.get_row(real_idx)
        event_trip_number = trip_number(saved_row) or google_sheet_row_value
        self._save_status_event(task_index=event_trip_number,
                                event_type="unload_done",
                                field_name=f"processed[{unload_idx}]",
                                old_value=str(old_processed),
                                new_value=str(new_processed),
                                message=f"Выгрузка #{unload_idx + 1} отмечена обработанной",
                                source="maps", )
        return True, saved_task, None

    def exists_row(self, real_idx: int) -> bool:
        data, err = self._get_data()
        if err or data is None:
            return False
        return 0 <= real_idx < len(data) and isinstance(data[real_idx], dict)

    def get_processible_rows(self) -> list[tuple[int, int | None]]:
        """Возвращает пары (real_row_idx, row_identity) для обработки навигации."""
        data, err = self._get_data()
        if err or data is None:
            return []

        result: list[tuple[int, int | None]] = []

        for row_idx, row in enumerate(data):
            if not isinstance(row, dict):
                continue
            if not row.get("id") or not row.get("ТС"):
                continue
            
            # Пропускать строки с будущими погрузками (подсвечены светло синим)
            if self._is_future_load(row):
                continue
                
            result.append((row_idx, row_identity_for_gui(row)))

        return result
    
    def _is_future_load(self, row: dict) -> bool:
        """Проверить, является ли погрузка будущей (более чем через 3 часа)"""
        from datetime import datetime, timedelta
        
        pg = row.get("Погрузка", [])
        if not (pg and isinstance(pg, list) and isinstance(pg[0], dict)):
            return False

        date_str = pg[0].get("Дата 1", "")
        time_str = pg[0].get("Время 1", "")

        try:
            if time_str and time_str.count(":") == 1:
                time_str += ":00"
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")

            # Пропускать если погрузка через более чем 3 дня
            return dt > datetime.now() + timedelta(hours=3)
        except Exception:
            return False

    def get_row_identity_by_row(self, real_idx: int) -> int | None:
        row = self.get_row(real_idx)
        if not row:
            return None
        return row_identity_for_gui(row)

    def get_index_key_by_row(self, real_idx: int) -> int | None:
        """Совместимый alias: раньше GUI row_identity называли index_key."""
        return self.get_row_identity_by_row(real_idx)

    def get_trip_number_by_row(self, real_idx: int) -> int | None:
        row = self.get_row(real_idx)
        if not row:
            return None
        return trip_number(row)

    # TODO: Временно на паузе
    def _save_status_event(self,
                           *,
                           task_index: int,
                           event_type: str,
                           field_name: str = "",
                           old_value: str = "",
                           new_value: str = "",
                           message: str = "",
                           source: str = "user", ) -> None:
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
