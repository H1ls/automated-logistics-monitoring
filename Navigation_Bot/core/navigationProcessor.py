from Navigation_Bot.bots.navigationBot import NavigationBot
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.bots.webDriverManager import WebDriverManager
from PyQt6.QtCore import QTimer
from concurrent.futures import ThreadPoolExecutor
from Navigation_Bot.core.paths import CONFIG_JSON

"""TODO 
        1.json_data → DataModel /отделить структуру хранения
        3.process_all() прогрессбар ?
"""


class NavigationProcessor:
    def __init__(self, json_data: list, logger, gsheet, filepath, display_callback, single_row=True, updated_rows=None):
        self.json_data = json_data
        self.log = logger
        self.gsheet = gsheet
        self.filepath = filepath
        self.display_callback = display_callback

        self._single_row_processing = single_row
        self.updated_rows = updated_rows if updated_rows is not None else []
        self.driver_manager = WebDriverManager(log_func=self.log)
        self.browser_opened = False
        self.navibot = None
        self.mapsbot = None

    def process_row_wrapper(self, row):
        try:
            self.ensure_driver_and_bots()  # вот сюда

            self._reload_json()
            if not self._valid_row(row):
                return

            car = self.json_data[row]

            updated = self._process_wialon_row(car)
            if not updated:
                return

            self._update_and_save(row, updated)
            self._process_maps_and_write(row, updated)
            self._finalize_row(updated)

        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")

    def ensure_driver_and_bots(self):
        if not self.browser_opened:
            self.driver_manager.start_browser()
            self.driver_manager.login_wialon()
            self.driver_manager.open_yandex_maps()
            self.browser_opened = True
            self.log("✅ Драйвер и вкладки готовы.")

        if not self.navibot:
            self.navibot = NavigationBot(self.driver_manager.driver, log_func=self.log)

        if not self.mapsbot:
            self.mapsbot = MapsBot(self.driver_manager.driver, log_func=self.log)

    def _reload_json(self):
        try:
            fresh = JSONManager(self.filepath, log_func=self.log).load_json() or []
            self.json_data = fresh
        except Exception as e:
            self.log(f"⚠️ Не удалось перезагрузить JSON перед обработкой: {e}")

    def _valid_row(self, row):
        if row >= len(self.json_data):
            self.log(f"⚠️ Строка {row} не существует.")
            return False
        if not self.json_data[row].get("ТС"):
            self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
            return False
        return True

    def _process_wialon_row(self, car):
        self.driver_manager.switch_to_tab("wialon")
        result = self.navibot.process_row(car, switch_to_wialon=False)
        if not result.get("_новые_координаты"):
            self.log(f"⚠️ Координаты не получены — пропуск Я.Карт для ТС {car.get('ТС')}")
            return None

        if "processed" in car:
            result["processed"] = car["processed"]

        return result

    def _update_and_save(self, row, updated):
        self.json_data[row].update(updated)
        JSONManager().save_in_json(self.json_data, self.filepath)

    def _process_maps_and_write(self, row, car):
        self.driver_manager.switch_to_tab("yandex")
        active_unload = self.get_first_unprocessed_unload(car)
        if active_unload:
            self.mapsbot.process_navigation_from_json(car, active_unload)

        self.updated_rows.append(car)
        JSONManager().save_in_json(self.json_data, self.filepath)

    def _finalize_row(self, car):
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)
            self.log("📤 Данные записаны в Google Sheets")

        QTimer.singleShot(0, self.display_callback)
        self.log(f"✅ Завершено для ТС: {car.get('ТС')}")

    @staticmethod
    def get_first_unprocessed_unload(car: dict) -> dict | None:
        processed = car.get("processed", [])
        unloads = car.get("Выгрузка", [])

        for i, done in enumerate(processed):
            if not done and i < len(unloads):
                return unloads[i]
        return None

    def process_all(self):
        self._single_row_processing = False
        self.updated_rows = []
        self.log("▶ Обработка всех ТС...")

        with ThreadPoolExecutor(max_workers=1) as executor:
            for row in range(len(self.json_data)):
                car = self.json_data[row]
                if not car.get("id") or not car.get("ТС"):
                    continue
                executor.submit(self.process_row_wrapper, row)

        QTimer.singleShot(5000, self.display_callback)

    def write_all_to_google(self):
        if self.updated_rows:
            self.gsheet.write_all(self.updated_rows)
            self.updated_rows = []
