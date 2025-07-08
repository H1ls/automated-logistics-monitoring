from Navigation_Bot.bots.navigationBot import NavigationBot
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.bots.webDriverManager import WebDriverManager
from PyQt6.QtCore import QTimer
from concurrent.futures import ThreadPoolExecutor
from Navigation_Bot.core.paths import CONFIG_JSON

"""TODO 1.process_row_wrapper() — слишком длинный
        2.json_data → DataModel /отделить структуру хранения
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
        self.driver_manager = None
        self.browser_opened = False
        self.navibot = None
        self.mapsbot = None

    def process_row_wrapper(self, row):
        try:
            if row >= len(self.json_data):
                self.log(f"⚠️ Строка {row} не существует.")
                return
            car = self.json_data[row]
            if not car.get("ТС"):
                self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
                return
            self.init_driver_if_needed()
            updated = self.process_wialon_row(car)
            if not updated.get("_новые_координаты"):
                self.log(f"⚠️ Координаты не получены в этом запуске — пропуск Я.Карт для ТС {updated.get('ТС')}")
                return
            self.update_json_and_switch_to_yandex(row, updated)
            self.process_maps_and_write(updated, row)

            QTimer.singleShot(0, self.display_callback)
            self.log(f"✅ Завершено для ТС: {updated.get('ТС')}")

        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")

    def init_driver_if_needed(self):
        if not self.browser_opened or not hasattr(self, "driver_manager"):
            self.driver_manager = WebDriverManager(log_func=self.log)
            self.driver_manager.start_browser()
            self.driver_manager.login_wialon()
            self.browser_opened = True
            self.log("✅ Драйвер и авторизация завершены.")

    def process_wialon_row(self, car):
        driver = self.driver_manager.driver
        driver.switch_to.window(driver.window_handles[0])
        self.log("🌐 Переключение на Wialon...")
        navibot = NavigationBot(driver, log_func=self.log)
        return navibot.process_row(car, switch_to_wialon=False)

    def update_json_and_switch_to_yandex(self, row, updated):
        updated.pop("_новые_координаты", None)
        # self.json_data[row] = updated
        self.json_data[row].update(updated)

        JSONManager().save_in_json(self.json_data, self.filepath)
        self.driver_manager.open_yandex_maps()

    def process_maps_and_write(self, car, row_idx):
        maps_bot = MapsBot(self.driver_manager.driver, log_func=self.log)
        maps_bot.process_navigation_from_json(car)
        self.updated_rows.append(car)

        self.json_data[row_idx] = car
        JSONManager().save_in_json(self.json_data, self.filepath)

        if self._single_row_processing:
            self.gsheet.append_to_cell(car)
            self.log("📤 Данные записаны в Google Sheets")

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
        if hasattr(self, "updated_rows") and self.updated_rows:
            try:
                self.gsheet.append_to_cell(self.updated_rows)
                self.log(f"📤 Обновлены все строки в Google Sheets ({len(self.updated_rows)} шт.)")
            except Exception as e:

                self.log(f"❌ Ошибка при групповой записи в Google Sheets: {e}")
            self.updated_rows = []
