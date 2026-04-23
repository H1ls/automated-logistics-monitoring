from __future__ import annotations

import traceback
from typing import Callable, Any
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper


class NavigationRowService:
    """
    Сервис обработки одной строки навигации:
    Wialon -> при необходимости Maps -> save -> finalize.
    """

    def __init__(self, data_context,
                 logger: Callable[[str], None],
                 gsheet,
                 tasks_service=None,
                 ui_bridge=None,
                 display_callback: Callable[[], None] | None = None,
                 single_row_processing: bool = True,
                 updated_rows: list | None = None, ):

        self.data_context = data_context
        self.log = logger
        self.gsheet = gsheet
        self.tasks_service = tasks_service
        self.ui_bridge = ui_bridge
        self.display_callback = display_callback
        self._single_row_processing = single_row_processing
        self.updated_rows = updated_rows if updated_rows is not None else []

    def _build_runtime_patch_from_task(self, task) -> dict:
        nav = task.navigation
        processing = task.processing

        patch = {"гео": nav.geo_text or "",
                 "коор": nav.coordinates or "",
                 "скорость": nav.speed_kmh if nav.speed_kmh is not None else 0,
                 "_новые_координаты": bool(nav.has_fresh_coordinates),
                 "processed": list(processing.processed_unloads), }

        legacy = self._task_to_legacy_row(task)

        if "gps_fix_age" in legacy:
            patch["gps_fix_age"] = legacy["gps_fix_age"]

        if "Маршрут" in legacy:
            patch["Маршрут"] = legacy["Маршрут"]

        return patch

    def _task_to_legacy_row(self, task):
        return TaskMapper.to_dict(task)

    def _apply_legacy_row_to_task(self, task, legacy_row):
        updated_task = TaskMapper.from_dict(legacy_row)

        task.navigation = updated_task.navigation
        task.forecast = updated_task.forecast
        task.processing = updated_task.processing

        return task

    def _should_process_maps(self, task) -> bool:
        nav = task.navigation
        return (bool(nav.has_fresh_coordinates)
                and bool(nav.coordinates)
                and ("," in str(nav.coordinates))
                )

    # TODO: исправить сохранения self._save_json() принудительно из RAM сохраняет в Disk для отображение в таблице
    def process_row(self, row: int, *, navibot, mapsbot, switch_tab: Callable[[str], bool], ) -> tuple[
        dict | None, int | None]:
        """
        Обработать одну строку.
        Возвращает:
            (merged_row, index_key)
        где:
            merged_row -> итоговая строка после обработки
            index_key  -> row["index"], если удалось определить
        """
        index_key = None
        try:
            self._reload_json()

            data = self.data_context.get() or []

            if 0 <= row < len(data):
                index_key = (data[row] or {}).get("index")

            if not self._valid_row(row, data):
                return None, index_key

            task = self.tasks_service.get_task(row) if self.tasks_service else None
            if not task:
                self.log(f"⚠️ Не удалось получить Task для строки {row}")
                return None, index_key

            updated_task = self._process_wialon_row(task=task, navibot=navibot, switch_tab=switch_tab)
            if not updated_task:
                return None, index_key

            should_maps = self._should_process_maps(updated_task)

            if should_maps:
                updated_task = self._process_maps(row=row, task=updated_task, mapsbot=mapsbot, switch_tab=switch_tab, )

            runtime_patch = self._build_runtime_patch_from_task(updated_task)
            merged = self._merge_row(row, runtime_patch)

            final_row = self.data_context.get()[row]
            self.updated_rows.append(dict(final_row))
            self._save_json()
            self._finalize_row(final_row)

            return merged, index_key

        except Exception as e:
            self.log(f"❌ Ошибка в NavigationRowService.process_row: {e}")
            self.log(traceback.format_exc())
            return None, index_key

    # TODO: Не делать _reload_json для batch mode, разгрузит
    def _reload_json(self) -> None:
        try:
            self.data_context.reload()
        except Exception as e:
            self.log(f"⚠️ Не удалось перезагрузить JSON перед обработкой: {e}")

    # TODO: _valid_row() всё ещё на dict "if not data[row].get("ТС")"
    def _valid_row(self, row: int, data: list) -> bool:
        try:
            if row < 0:
                self.log(f"⚠️ Некорректный индекс строки: {row}")
                return False

            if row >= len(data):
                self.log(f"⚠️ Строка {row} не существует.")
                return False

            if not data[row].get("ТС"):
                self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
                return False

            return True

        except Exception as e:
            self.log(f"⚠️ _valid_row error: {e}")
            return False

    def _merge_row(self, row: int, updated: dict) -> dict:
        json_data = self.data_context.get()
        json_data[row].update(updated)
        return json_data[row]

    # TODO: убрать reload, и работать через in-memory state
    def _save_json(self) -> None:
        self.data_context.save()

    def _apply_navigation_result_to_task(self, task, result):

        task.navigation.gps_fix_text = result.gps_fix_text or ""
        task.navigation.gps_fix_age_seconds = result.gps_fix_age_seconds
        task.navigation.geo_text = result.geo_text or ""
        task.navigation.coordinates = result.coordinates
        task.navigation.speed_kmh = result.speed_kmh
        task.navigation.has_fresh_coordinates = bool(result.has_fresh_coordinates)
        return task

    def _process_wialon_row(self, *, task, navibot, switch_tab: Callable[[str], bool]):
        try:
            if not switch_tab("gps.skyglonass"):
                return None

            legacy_row = self._task_to_legacy_row(task)
            result = navibot.process_vehicle_row(legacy_row)
            if not result:
                return None

            task = self._apply_navigation_result_to_task(task, result)

            if not task.navigation.has_fresh_coordinates:
                self.log(f"⚠️ Координаты не получены — пропуск Я.Карт для ТС {task.vehicle.plate_number}")

            return task

        except Exception as e:
            self.log(f"⛔ Ошибка _process_wialon_row: {e}")
            self.log(traceback.format_exc())
            return None

    # TODO: добавить слежение что стоит/покинул Выгрузку N
    def _process_maps(self, *, row: int, task, mapsbot, switch_tab):
        if not switch_tab("yandex"):
            return task

        if not self.tasks_service:
            self.log("⚠️ TasksService не подключён")
            return task

        active_unload = task.get_first_unprocessed_unload()
        if not active_unload:
            return task

        unload_idx, unload_point = active_unload
        source_row = dict(self.data_context.get()[row] or {})
        legacy_row = self._task_to_legacy_row(task)
        legacy_row["Погрузка"] = source_row.get("Погрузка", [])
        legacy_row["Выгрузка"] = source_row.get("Выгрузка", [])
        legacy_row["raw_load"] = source_row.get("raw_load", "")
        legacy_row["raw_unload"] = source_row.get("raw_unload", "")

        mapsbot.process_navigation_from_point(legacy_row, unload_point)
        task = self._apply_legacy_row_to_task(task, legacy_row)

        if task.navigation.geo_text == "у выгрузки":
            index_key = task.index
            if index_key is None:
                self.log("⚠️ Нельзя отметить выгрузку обработанной: нет index")
                return task

            ok, saved_task, err = self.tasks_service.mark_unload_processed(index_key, unload_idx)
            if not ok:
                self.log(f"⚠️ Не удалось отметить выгрузку обработанной: {err}")
                return task

            if saved_task:
                task.processing = saved_task.processing

        return task

    # TODO: разделить на 3 heplers, _sync_single_row_to_google(car), _refresh_ui, _log_finalize(car)
    def _finalize_row(self, car: dict) -> None:
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)

        if self.ui_bridge:
            self.ui_bridge.refresh.emit()
        elif self.display_callback:
            self.display_callback()

        self.log(f"✅ Завершено для ТС: {car.get('ТС')}")

    def set_single_row_processing(self, enabled: bool) -> None:
        self._single_row_processing = enabled
