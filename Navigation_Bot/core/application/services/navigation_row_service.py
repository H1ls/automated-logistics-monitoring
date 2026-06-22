from __future__ import annotations

import traceback
from typing import Callable, Any
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper
from Navigation_Bot.core.domain.entities.navigation_snapshot import NavigationSnapshot
from Navigation_Bot.core.domain.entities.route_estimate import RouteEstimate


class NavigationRowService:
    """
    Сервис обработки одной строки навигации:
    Wialon -> при необходимости Maps -> save -> finalize.
    """

    def __init__(self,
                 logger: Callable[[str], None],
                 gsheet,
                 tasks_service=None,
                 ui_bridge=None,
                 display_callback: Callable[[], None] | None = None,
                 single_row_processing: bool = True,
                 updated_rows: list | None = None,
                 navigation_history_service=None,
                 route_estimate_history_service=None,
                 ):

        self.log = logger
        self.gsheet = gsheet
        self.tasks_service = tasks_service
        self.ui_bridge = ui_bridge
        self.display_callback = display_callback
        self._single_row_processing = single_row_processing
        self.updated_rows = updated_rows if updated_rows is not None else []
        self.navigation_history_service = navigation_history_service
        self.route_estimate_history_service = route_estimate_history_service
        self._pending_navigation_snapshots: list[NavigationSnapshot] = []
        self._pending_route_estimates: list[RouteEstimate] = []

    # TODO: Найти нормальное место для _save_route_estimate
    def _save_route_estimate(self, task, unload_idx: int, task_trip_number: int | None) -> None:
        try:
            if not self.route_estimate_history_service:
                return

            forecast = task.forecast

            estimate = RouteEstimate(trip_number=task_trip_number or task.index,
                                     target_sequence=unload_idx + 1,
                                     distance_km=forecast.distance_km,
                                     duration_minutes=forecast.duration_minutes,
                                     arrival_time=forecast.arrival_time,
                                     on_time=forecast.on_time,
                                     buffer_minutes=forecast.buffer_minutes,
                                     time_buffer_text=forecast.time_buffer_text,
                                     )

            if self._single_row_processing:
                self.route_estimate_history_service.append(estimate)
            else:
                self._pending_route_estimates.append(estimate)
        except Exception as e:
            self.log(f"❌ Ошибка в NavigationRowService._save_route_estimate: {e}")

    # TODO: Найти нормальное место для _save_navigation_snapshot
    def _save_navigation_snapshot(self, task, task_trip_number: int | None) -> None:
        try:
            if not self.navigation_history_service:
                return

            nav = task.navigation

            snapshot = NavigationSnapshot(trip_number=task_trip_number or task.index,
                                          vehicle_plate=task.vehicle.plate_number,
                                          vehicle_monitoring_id=task.vehicle.monitoring_id,
                                          geo_text=nav.geo_text or "",
                                          coordinates=nav.coordinates or "",
                                          speed_kmh=nav.speed_kmh,
                                          gps_fix_text=nav.gps_fix_text or "",
                                          gps_fix_age_seconds=nav.gps_fix_age_seconds,
                                          has_fresh_coordinates=bool(nav.has_fresh_coordinates),
                                          is_navigation_stale=bool(nav.gps_fix_age_seconds is not None
                                                                   and nav.gps_fix_age_seconds >= 3600),
                                          )

            if self._single_row_processing:
                self.navigation_history_service.append(snapshot)
            else:
                self._pending_navigation_snapshots.append(snapshot)
        except Exception as e:
            self.log(f"❌ Ошибка в NavigationRowService._save_navigation_snapshot: {e}")

    def _build_runtime_patch_from_task(self, task) -> dict:
        nav = task.navigation
        processing = task.processing

        patch = {"гео": nav.geo_text or "",
                 "коор": nav.coordinates or "",
                 "скорость": nav.speed_kmh if nav.speed_kmh is not None else 0,
                 "_новые_координаты": bool(nav.has_fresh_coordinates),
                 "processed": list(processing.processed_unloads),
                 }

        legacy = self._task_to_legacy_row(task)

        if "gps_fix_age" in legacy:
            patch["gps_fix_age"] = legacy["gps_fix_age"]

        if "Маршрут" in legacy:
            patch["Маршрут"] = legacy["Маршрут"]

        return patch

    def flush_history_buffers(self) -> None:
        self._flush_items(self.navigation_history_service,
                          self._pending_navigation_snapshots,
                          "navigation snapshots")
        self._flush_items(self.route_estimate_history_service,
                          self._pending_route_estimates,
                          "route estimates")

    def _flush_items(self, service, items: list, label: str) -> None:
        if not service or not items:
            return
        batch = list(items)
        items.clear()
        try:
            if hasattr(service, "append_many"):
                service.append_many(batch)
            else:
                for item in batch:
                    service.append(item)
        except Exception as e:
            self.log(f"Failed to save batch {label}: {e}")

    def _task_to_legacy_row(self, task):
        return TaskMapper.to_dict(task)

    def _apply_legacy_row_to_task(self, task, legacy_row):
        updated_task = TaskMapper.from_dict(legacy_row)

        task.navigation = updated_task.navigation
        task.forecast = updated_task.forecast
        task.processing = updated_task.processing
        task.route_plan = updated_task.route_plan

        return task

    def _should_process_maps(self, task) -> bool:
        nav = task.navigation
        return (bool(nav.has_fresh_coordinates)
                and bool(nav.coordinates)
                and ("," in str(nav.coordinates))
                )

    def process_row(self, row: int, *, navibot, mapsbot, switch_tab: Callable[[str], bool], ) -> tuple[
        dict | None, int | None]:
        """
        Обработать одну строку.
        Возвращает:
            (merged_row, row_identity)
        где:
            merged_row -> итоговая строка после обработки
            row_identity -> ключ GUI: google_sheet_row, иначе trip_number
        """
        row_identity = None

        try:
            row_identity = self.tasks_service.get_row_identity_by_row(row)
            task_trip_number = self.tasks_service.get_trip_number_by_row(row)
            if not self.tasks_service.exists_row(row):
                self.log(f"⚠️ Строка {row} не существует.")
                return None, row_identity

            task = self.tasks_service.get_task(row)
            if not task:
                self.log(f"⚠️ Не удалось получить Task для строки {row}")
                return None, row_identity

            if not task.vehicle.plate_number:
                self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
                return None, row_identity

            updated_task = self._process_wialon_row(task=task, navibot=navibot, switch_tab=switch_tab)
            if not updated_task:
                return None, row_identity

            self._save_navigation_snapshot(updated_task, task_trip_number)
            should_maps = self._should_process_maps(updated_task)

            if should_maps:
                updated_task = self._process_maps(task=updated_task, mapsbot=mapsbot, switch_tab=switch_tab,
                                                  task_trip_number=task_trip_number, )

            ok, saved_task, err = self.tasks_service.save_task(row, updated_task)
            if not ok:
                self.log(f"❌ Не удалось сохранить Task: {err}")
                return None, row_identity

            final_row = TaskMapper.to_dict(updated_task)
            if not final_row:
                self.log(f"⚠️ После сохранения строка {row} не найдена")
                return None, row_identity

            self.updated_rows.append(dict(final_row))
            self._finalize_row(final_row)

            return final_row, row_identity
        except Exception as e:
            self.log(f"❌ Ошибка в NavigationRowService.process_row:")
            # self.log(e)
            # self.log(traceback.format_exc())
            return None, row_identity

    def _apply_navigation_result_to_task(self, task, result):

        task.navigation.gps_fix_text = result.gps_fix_text or ""
        task.navigation.gps_fix_age_seconds = result.gps_fix_age_seconds
        task.navigation.geo_text = result.geo_text or ""
        task.navigation.geo_zona = result.geo_zona or ""
        task.navigation.coordinates = result.coordinates
        task.navigation.speed_kmh = result.speed_kmh
        task.navigation.has_fresh_coordinates = bool(result.has_fresh_coordinates)
        return task

    def _process_wialon_row(self, *, task, navibot, switch_tab: Callable[[str], bool]):
        try:
            if not switch_tab("gps.skyglonass"):
                return None

            legacy_row = self._task_to_legacy_row(task)

            if hasattr(navibot, "process_vehicle_row"):
                result = navibot.process_vehicle_row(legacy_row)
            else:
                result = navibot.process_row(legacy_row)

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
    # TODO: Привязать
    def _process_maps(self, *, task, mapsbot, switch_tab, task_trip_number: int | None):
        if not switch_tab("yandex"):
            return task

        if not self.tasks_service:
            self.log("⚠️ TasksService не подключён")
            return task

        active_unload = task.get_first_unprocessed_unload()
        if not active_unload:
            return task

        unload_idx, unload_point = active_unload
        legacy_row = self._task_to_legacy_row(task)

        mapsbot.process_navigation_from_point(legacy_row, unload_point)
        #TODO: Доделать
        # MapsBot по-прежнему является устаревшим компонентом и записывает вычисленный маршрут в
        # ``Маршрут``. TaskMapper.to_dict также помещает предыдущее каноническое значение
        # ``route_estimate`` в legacy_row, а TaskMapper.from_dict присваивает этому полю
        # приоритет. Удаляем устаревшее каноническое значение, чтобы новый результат MapsBot
        # был преобразован в task.forecast и впоследствии сохранен.
        legacy_row.pop("route_estimate", None)
        task = self._apply_legacy_row_to_task(task, legacy_row)

        self._save_route_estimate(task, unload_idx, task_trip_number)
        if task.navigation.geo_text == "у выгрузки":
            google_sheet_row = task.index
            if google_sheet_row is None:
                self.log("⚠️ Нельзя отметить выгрузку обработанной: нет google_sheet_row")
                return task

            ok, saved_task, err = self.tasks_service.mark_unload_processed(google_sheet_row, unload_idx)
            if not ok:
                self.log(f"⚠️ Не удалось отметить выгрузку обработанной: {err}")
                return task

            if saved_task:
                task.processing = saved_task.processing

        return task

    def _finalize_row(self, car: dict) -> None:
        self._sync_single_row_to_google(car)
        self._refresh_ui()
        self._log_finalize(car)

    def _sync_single_row_to_google(self, car: dict) -> None:
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)

    def _refresh_ui(self) -> None:
        if self.ui_bridge:
            self.ui_bridge.refresh.emit()
        elif self.display_callback:
            self.display_callback()

    def _log_finalize(self, car: dict) -> None:
        self.log(f"✅ Завершено для ТС: {car.get('ТС')}")

    def set_single_row_processing(self, enabled: bool) -> None:
        self._single_row_processing = enabled

    def _format_buffer(self, minutes: int) -> str:
        if minutes is None:
            return ""

        hours = minutes // 60
        mins = minutes % 60

        if hours and mins:
            return f"{hours}ч {mins}м"
        if hours:
            return f"{hours}ч"
        return f"{mins}м"

    def _format_route_estimate_text(self, estimate: dict) -> str:
        buffer_text = self._format_buffer(estimate.get("buffer_minutes", 0))

        return (f"{estimate.get('calculated_at', '')} | "
                f"Едет к выгрузке #{estimate.get('target_sequence', '')} | "
                f"Осталось {estimate.get('distance_km', 0)} км | "
                f"ETA {estimate.get('arrival_time', '')} | "
                f"Запас {buffer_text}"
                )
