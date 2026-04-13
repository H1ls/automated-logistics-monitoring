from __future__ import annotations

import traceback
from typing import Callable, Any


class NavigationRowService:
    """
    Сервис обработки одной строки навигации:
    Wialon -> при необходимости Maps -> save -> finalize.
    """

    def __init__(self, data_context,
                 logger: Callable[[str], None],
                 gsheet, ui_bridge=None,
                 display_callback: Callable[[], None] | None = None,
                 single_row_processing: bool = True,
                 updated_rows: list | None = None, ):

        self.data_context = data_context
        self.log = logger
        self.gsheet = gsheet
        self.ui_bridge = ui_bridge
        self.display_callback = display_callback
        self._single_row_processing = single_row_processing
        self.updated_rows = updated_rows if updated_rows is not None else []

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

            if not self._valid_row(row):
                return None, index_key

            car = self.data_context.get()[row]

            updated = self._process_wialon_row(car=car, navibot=navibot, switch_tab=switch_tab, )
            if not updated:
                return None, index_key

            merged = self._merge_row(row, updated)

            should_maps = (bool(merged.get("_новые_координаты"))
                           and bool(merged.get("коор"))
                           and ("," in str(merged["коор"])))

            if should_maps:
                merged = self._process_maps(row=row, car=merged, mapsbot=mapsbot, switch_tab=switch_tab, )

            self.updated_rows.append(merged)
            self._save_json()
            self._finalize_row(merged)

            return merged, index_key

        except Exception as e:
            self.log(f"❌ Ошибка в NavigationRowService.process_row: {e}")
            self.log(traceback.format_exc())
            return None, index_key

    def _reload_json(self) -> None:
        try:
            self.data_context.reload()
        except Exception as e:
            self.log(f"⚠️ Не удалось перезагрузить JSON перед обработкой: {e}")

    def _valid_row(self, row: int) -> bool:
        try:
            data = self.data_context.get() or []

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

    def _save_json(self) -> None:
        self.data_context.save()

    def _process_wialon_row(self, *, car: dict, navibot, switch_tab: Callable[[str], bool], ) -> dict | None:
        try:
            if not switch_tab("gps.skyglonass"):
                return None

            result = navibot.process_row(car)
            if not result:
                return None

            if "processed" in car and "processed" not in result:
                result["processed"] = car["processed"]

            if not result.get("_новые_координаты"):
                self.log(f"⚠️ Координаты не получены — пропуск Я.Карт для ТС {car.get('ТС')}")

            return result

        except Exception as e:
            self.log(f"⛔ Ошибка _process_wialon_row: {e}")
            self.log(traceback.format_exc())
            return None

    def _process_maps(self, *, row: int, car: dict, mapsbot, switch_tab: Callable[[str], bool], ) -> dict:
        if not switch_tab("yandex"):
            return car

        active_unload = self.get_first_unprocessed_unload(car)
        if active_unload:
            mapsbot.process_navigation_from_json(car, active_unload)

        self._merge_row(row, car)
        return self.data_context.get()[row]

    def _finalize_row(self, car: dict) -> None:
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)

        if self.ui_bridge:
            self.ui_bridge.refresh.emit()
        elif self.display_callback:
            self.display_callback()

        self.log(f"✅ Завершено для ТС: {car.get('ТС')}")

    @staticmethod
    def get_first_unprocessed_unload(car: dict) -> dict | None:
        processed = car.get("processed", [])
        unloads = car.get("Выгрузка", [])

        for i, done in enumerate(processed):
            if not done and i < len(unloads):
                return unloads[i]
        return None

    def set_single_row_processing(self, enabled: bool) -> None:
        self._single_row_processing = enabled
