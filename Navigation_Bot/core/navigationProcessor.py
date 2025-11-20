from PyQt6.QtCore import QTimer
from concurrent.futures import ThreadPoolExecutor
import traceback
from Navigation_Bot.bots.webDriverManager import WebDriverManager
from Navigation_Bot.bots.navigationBot import NavigationBot
from Navigation_Bot.bots.mapsBot import MapsBot


class NavigationProcessor:
    def __init__(self, data_context, logger, gsheet, filepath, display_callback, single_row, updated_rows,
                 executor=None, highlight_callback=None,browser_rect=None):
        self.data_context = data_context
        self.log = logger
        self.gsheet = gsheet
        self.filepath = filepath
        self.display_callback = display_callback

        self._single_row_processing = single_row
        self.updated_rows = updated_rows if updated_rows is not None else []

        self.browser_rect = browser_rect
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.highlight_cb = highlight_callback

        self.driver_manager = WebDriverManager(log_func=self.log)
        self.browser_opened = False
        self.navibot = None
        self.mapsbot = None

    def on_row_click(self, row_idx: int):
        data = self.data_context.get() or []
        if not (0 <= row_idx < len(data)):
            if self.log:
                self.log(f"⚠️ Строка {row_idx} больше не существует. Пропуск.")
            return

        # Подсветка строки, через переданный колбэк из GUI
        if self.highlight_cb:
            try:
                self.highlight_cb(row_idx)
            except Exception as e:
                if self.log:
                    self.log(f"⚠️ Ошибка подсветки строки {row_idx}: {e}")

        # Запуск обработки в фоне
        if self.executor:
            self.executor.submit(self.process_row_wrapper, row_idx)
        else:
            with ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(self.process_row_wrapper, row_idx)

    def process_row_wrapper(self, row):
        try:
            self.ensure_driver_and_bots()
            self._reload_json()

            if not self._valid_row(row):
                return

            car = self.data_context.get()[row]
            updated = self._process_wialon_row(car)
            if not updated:
                return

            self._update_and_save(row, updated)
            self._process_maps_and_write(row, updated)
            self._finalize_row(updated)
        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")
            self.log(traceback.format_exc())

    def ensure_driver_and_bots(self):
        """Готовим браузер и ботов:
        - один раз при первом ▶,
        - либо после падения/закрытия браузера.
        """
        # 1. Если драйвер отсутствует или умер – сбрасываем состояние
        driver = getattr(self.driver_manager, "driver", None)
        if not driver or not self.driver_manager.is_alive():
            self.browser_opened = False
            self.navibot = None
            self.mapsbot = None

        # Если браузер ещё не открыт – стартуем и открываем вкладки
        if not self.browser_opened:

            self.driver_manager.start_browser(self.browser_rect)
            self.driver_manager.login_wialon()  # один раз: Wialon + Мониторинг
            self.driver_manager.open_yandex_maps()  # один раз: Я.Карты
            self.browser_opened = True
            self.log("✅ Драйвер и вкладки готовы.")

        # Создаём ботов, если их ещё нет
        if not self.navibot:
            self.navibot = NavigationBot(self.driver_manager.driver, log_func=self.log)

        if not self.mapsbot:
            self.mapsbot = MapsBot(self.driver_manager, log_func=self.log)

    def _reload_json(self):
        try:
            self.data_context.reload()
        except Exception as e:
            self.log(f"⚠️ Не удалось перезагрузить JSON перед обработкой: {e}")

    def _valid_row(self, row):
        try:
            if row >= len(self.data_context.get()):
                self.log(f"⚠️ Строка {row} не существует.")
                return False
            if not self.data_context.get()[row].get("ТС"):
                self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
                return False
            return True
        except:
            print("_valid_row")

    def _process_wialon_row(self, car):
        try:
            self.driver_manager.switch_to_tab("wialon")
            result = self.navibot.process_row(car, switch_to_wialon=False)
            if not result.get("_новые_координаты"):
                self.log(f"⚠️ Координаты не получены — пропуск Я.Карт для ТС {car.get('ТС')}")
                return None

            if "processed" in car:
                result["processed"] = car["processed"]

            return result
        except:
            print("❌ Ошибка _process_wialon_row")

    def _update_and_save(self, row, updated):
        json_data = self.data_context.get()
        json_data[row].update(updated)
        self.data_context.save()

    def _process_maps_and_write(self, row, car):
        if not self.driver_manager.switch_to_tab("yandex"):
            self.log("⛔ Не удалось переключиться на Яндекс.Карты — пропускаю расчёт маршрута.")
            return

        active_unload = self.get_first_unprocessed_unload(car)
        if active_unload:
            self.mapsbot.process_navigation_from_json(car, active_unload)

        json_data = self.data_context.get()
        json_data[row].update(car)

        self.updated_rows.append(car)
        self.data_context.save()

    def _finalize_row(self, car):
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)
            # self.log("📤 Данные записаны в Google Sheets")

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
            for row in range(len(self.data_context.get())):
                car = self.data_context.get()[row]
                if not car.get("id") or not car.get("ТС"):
                    continue
                executor.submit(self.process_row_wrapper, row)

        QTimer.singleShot(5000, self.display_callback)

    def write_all_to_google(self):
        if self.updated_rows:
            self.gsheet.write_all(self.updated_rows)
            self.updated_rows = []
