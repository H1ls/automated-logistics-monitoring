from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.processed_flags import init_processed_flags


@dataclass(slots=True)
class TasksService:
    data_context: Any
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def _get_data(self) -> tuple[list | None, str | None]:
        data = self.data_context.get()
        if data is None:
            return None, "data_context_empty"
        if not isinstance(data, list):
            return None, "data_context_invalid"
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
        self.data_context.save()
        return True, removed, None

    def sync_processed(self) -> tuple[bool, str | None]:
        data, err = self._get_data()
        if err:
            return False, err

        init_processed_flags(data, data, loads_key="Выгрузка")
        self.data_context.save()
        return True, None

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
            self.data_context.save()

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
        self.data_context.save()

        return True, new_task, None

    def build_row_from_google_dh(self, index_key: int, dh: list[str]) -> dict:
        d = dh[0] if len(dh) > 0 else ""
        e = dh[1] if len(dh) > 1 else ""
        f = dh[2] if len(dh) > 2 else ""
        g = dh[3] if len(dh) > 3 else ""
        h = dh[4] if len(dh) > 4 else ""

        raw_ts = re.sub(r"\s+", "", d)
        number, phone = raw_ts[:9], raw_ts[9:]
        formatted_ts = number[:6] + " " + number[6:] if len(number) >= 9 else number

        return {"index": index_key,
                "ТС": formatted_ts,
                "Телефон": phone,
                "ФИО": e,
                "КА": f,
                "Погрузка": g,
                "Выгрузка": h,
                "raw_load": g,
                "raw_unload": h, }

    def sync_rows_from_google(self, rows_map: dict[int, list[str]]) -> tuple[bool, dict | None, str | None]:
        """
        Массовая синхронизация локального data_context из данных Google.
        rows_map:
            {row_index: [D, E, F, G, H],
                ...}
        Поведение:
        - обновляет существующие строки по index
        - добавляет новые строки
        - удаляет локальные строки, которых нет среди активных Google rows
        - пересчитывает processed
        - сохраняет data_context

        Возвращает:
            (ok, stats, err)
        где stats = {"updated": int, "added": int, "deleted": int}
        """
        data, err = self._get_data()
        if err:
            return False, None, err

        if not isinstance(rows_map, dict):
            return False, None, "rows_map_invalid"

        existing_data = [row for row in data if isinstance(row, dict)]
        existing_indexes = {row.get("index") for row in existing_data if row.get("index") is not None}
        by_index = {row.get("index"): row
                    for row in existing_data
                    if row.get("index") is not None}

        active_indexes: set[int] = set()
        new_entries: list[dict] = []
        updated_count = 0

        for index_key, dh in rows_map.items():
            if not isinstance(index_key, int):
                continue

            if not isinstance(dh, list):
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

            active_indexes.add(index_key)

            if index_key in existing_indexes:
                old = by_index.get(index_key)
                if old is None:
                    continue

                changed = False
                for k, v in fresh.items():
                    if old.get(k) != v:
                        old[k] = v
                        changed = True

                if changed:
                    updated_count += 1
            else:
                new_entries.append(dict(fresh))

        if not active_indexes and not new_entries:
            return False, None, "no_active_rows"

        filtered_data = [row for row in existing_data if row.get("index") in active_indexes]
        deleted_count = len(existing_data) - len(filtered_data)

        result_data = filtered_data + new_entries

        init_processed_flags(result_data, existing_data, loads_key="Выгрузка")
        self.data_context.set(result_data)

        stats = {
            "updated": updated_count,
            "added": len(new_entries),
            "deleted": deleted_count,
        }
        return True, stats, None

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

        existing_indexes = {
            row.get("index")
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
            if not any([
                fresh.get("ТС"),
                fresh.get("Телефон"),
                fresh.get("ФИО"),
                fresh.get("КА"),
                fresh.get("Погрузка"),
                fresh.get("Выгрузка"),
            ]):
                continue

            data.append(fresh)
            existing_indexes.add(index_key)
            added_count += 1

        init_processed_flags(data, data, loads_key="Выгрузка")
        self.data_context.save()

        return True, {
            "added": added_count,
            "skipped_existing": skipped_existing,
        }, None

    def remove_completed_tasks(self, active_google_indexes: set[int]) -> tuple[bool, dict | None, str | None]:
        """
        Удаляет из локального data_context строки, которых больше нет среди активных строк Google.
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
            self.data_context.set(filtered)

        return True, {"deleted": deleted_count}, None
