# Navigation_Bot\core\navigationProcessor.py
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtWidgets import QTableWidgetItem

from LogistX.onec.bot import OneCBot
from LogistX.onec.context import RaceContext
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.scenarios.NavigationBot import NavigationBot
from Navigation_Bot.bots.webDriverManager import WebDriverManager
from Navigation_Bot.bots.scenarios.ReportsBot import WialonReportsBot


class NavigationProcessor:
    def __init__(self, data_context, logger, gsheet, filepath, display_callback, single_row, updated_rows,
                 executor=None, highlight_callback=None, browser_rect=None, ui_bridge=None):
        self.data_context = data_context
        self.log = logger
        self.gsheet = gsheet
        self.filepath = filepath
        self.display_callback = display_callback
        self.ui = ui_bridge
        self._single_row_processing = single_row
        self.updated_rows = updated_rows if updated_rows is not None else []

        self.browser_rect = browser_rect
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.highlight_cb = highlight_callback

        self.driver_manager = WebDriverManager(log_func=self.log)
        self.browser_opened = False
        self.navibot = None
        self.mapsbot = None
        self._is_processing = False
        self.ui_bridge = ui_bridge

    def _merge_row(self, row: int, updated: dict) -> dict:
        """Обновляет строку в data_context, но НЕ сохраняет"""
        json_data = self.data_context.get()
        json_data[row].update(updated)
        return json_data[row]

    def _save_json(self) -> None:
        """Единая точка сохранения"""
        self.data_context.save()

    def _switch_tab_or_log(self, name: str) -> bool:
        ok = self.driver_manager.switch_to_tab(name)
        if ok:
            return True

        # запасной вариант: если в navibot есть страховка — пробуем
        if name == "gps.skyglonass" and self.navibot and hasattr(self.navibot, "_ensure_on_wialon_tab"):
            try:
                if self.navibot._ensure_on_wialon_tab():
                    return True
            except Exception:
                pass

        self.log(f"⛔ Не удалось переключиться на вкладку: {name}")
        return False

    def on_row_click(self, row_idx: int):
        if self._is_processing:
            if self.log:
                self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return

        data = self.data_context.get() or []
        #  сначала проверка границ
        if not (0 <= row_idx < len(data)):
            if self.log:
                self.log(f"⚠️ Строка {row_idx} больше не существует. Пропуск.")
            return

        car = data[row_idx] or {}
        #  теперь можно включать блокировку
        self._is_processing = True

        index_key = car.get("index")
        if self.ui_bridge and index_key is not None:
            self.ui_bridge.set_busy.emit(index_key, True)

        # Подсветка строки (по ключу записи index)
        if self.highlight_cb:
            try:
                if index_key is None:
                    if self.log:
                        self.log(f"⚠️ Нет поля 'index' у строки {row_idx}. Подсветка пропущена.")
                else:
                    self.highlight_cb(index_key)
            except Exception as e:
                if self.log:
                    self.log(f"⚠️ Ошибка подсветки строки {row_idx}: {e}")

        # Запуск обработки в фоне
        if self.executor:
            self.executor.submit(self.process_row_wrapper, row_idx)
        else:
            with ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(self.process_row_wrapper, row_idx)

    def process_row_wrapper(self, row: int):
        index_key = None
        try:
            self.ensure_driver_and_bots()
            self._reload_json()

            data = self.data_context.get() or []
            if 0 <= row < len(data):
                index_key = (data[row] or {}).get("index")

            if not self._valid_row(row):
                return

            car = self.data_context.get()[row]

            updated = self._process_wialon_row(car)
            if not updated:
                return

            merged = self._merge_row(row, updated)

            should_maps = (bool(merged.get("_новые_координаты"))
                           and bool(merged.get("коор"))
                           and ("," in str(merged["коор"])))

            if should_maps:
                merged = self._process_maps(row, merged)

            self.updated_rows.append(merged)
            self._save_json()
            self._finalize_row(merged)

        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")
            self.log(traceback.format_exc())
        finally:
            self._is_processing = False
            if self.ui_bridge and index_key is not None:
                self.ui_bridge.set_busy.emit(index_key, False)

    def ensure_driver_and_bots(self):
        """Готовим браузер и ботов:
        - один раз при первом ▶,
        - либо после падения/закрытия браузера
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
            self._uilog("✅ Драйвер и вкладки готовы.")

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

    def _process_wialon_row(self, car: dict) -> dict | None:
        try:
            # if not self._switch_tab_or_log("wialon"):
            if not self._switch_tab_or_log("gps.skyglonass"):
                return None

            result = self.navibot.process_row(car)
            if not result:
                return None

            # сохраняем processed, если было
            if "processed" in car and "processed" not in result:
                result["processed"] = car["processed"]

            # если координаты не обновились — лог, но не ошибка
            if not result.get("_новые_координаты"):
                self.log(f"⚠️ Координаты не получены — пропуск Я.Карт для ТС {car.get('ТС')}")

            return result

        except Exception as e:
            self.log(f"⛔ Ошибка _process_wialon_row: {e}")
            self.log(traceback.format_exc())
            return None

    def _process_maps(self, row: int, car: dict) -> dict:
        if not self._switch_tab_or_log("yandex"):
            return car

        active_unload = self.get_first_unprocessed_unload(car)
        if active_unload:
            self.mapsbot.process_navigation_from_json(car, active_unload)

        # после mapsbot могли поменяться поля в car
        self._merge_row(row, car)
        return self.data_context.get()[row]

    def _finalize_row(self, car):
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)
            # self.log("📤 Данные записаны в Google Sheets")

        if self.ui_bridge:
            self.ui_bridge.refresh.emit()
        else:
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

    def process_all(self):
        # Не стартуем второй batch/single во время текущей обработки
        if self._is_processing:
            self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return

        self._is_processing = True
        prev_single_mode = self._single_row_processing
        self._single_row_processing = False
        self.updated_rows = []
        self.log("▶ Обработка всех ТС...")

        data = self.data_context.get() or []
        rows = [i for i, car in enumerate(data)
                if isinstance(car, dict) and car.get("id") and car.get("ТС")]

        # Нечего обрабатывать
        if not rows:
            self._is_processing = False
            self._single_row_processing = prev_single_mode
            if self.ui_bridge:
                self.ui_bridge.refresh.emit()
            else:
                self.display_callback()
            self.log("ℹ️ Нет строк для обработки.")
            return

        # Ждём completion в отдельном daemon-потоке, чтобы не блокировать GUI
        def _run_batch():
            try:
                futures = [self.executor.submit(self.process_row_wrapper, row) for row in rows]
                for f in futures:
                    f.result()
            except Exception as e:
                self.log(f"❌ Ошибка batch-обработки: {e}")
                self.log(traceback.format_exc())
            finally:
                self._is_processing = False
                self._single_row_processing = prev_single_mode
                if self.ui_bridge:
                    self.ui_bridge.refresh.emit()
                else:
                    self.display_callback()
                self.log("✅ Обработка всех ТС завершена")

        threading.Thread(target=_run_batch, daemon=True).start()

    def write_all_to_google(self):
        if self.updated_rows:
            self.gsheet.write_all(self.updated_rows)
            self.updated_rows = []

    def _uilog(self, msg: str):
        if getattr(self, "ui_bridge", None):
            self.ui_bridge.log.emit(msg)
        else:
            self.log(msg)

    def close_race_logistx_async(self, job_data: dict, on_done=None):
        """
        Асинхронное закрытие рейса из LogistX.

        job_data должен содержать:
          - row: int (номер строки на странице LogistX)
          - obj: dict (сама строка-объект, которую обновляем по результату)
          - race_no: str
          - unit: str
          - load_zone: str
          - unload_zone: str

        on_done (опционально) вызывается в GUI-потоке:
          on_done(ctx, result, job_data)
        """
        self.ensure_driver_and_bots()
        self._ensure_onec_dependencies()

        fut = self.executor.submit(self._job_close_race, job_data)
        if not on_done:
            # по умолчанию логируем результат в UI
            def on_done(ctx, result, _job):
                race_no = getattr(ctx, "race_name", "") or _job.get("race_no", "")
                if result.get("ok"):
                    self._uilog(f"✅ {race_no}: {result.get('message')}")
                else:
                    self._uilog(f"❌ {race_no}: {result.get('message')}")

        def _apply():
            try:
                ctx, result = fut.result()
                on_done(ctx, result, job_data)
            except Exception as e:
                self._uilog(f"❌ Ошибка close_race_logistx_async: {e}")

        # Все UI-вызовы — через мост (GUI-thread)
        if getattr(self, "ui_bridge", None):
            fut.add_done_callback(lambda _f: self.ui_bridge.call.emit(_apply))
        else:
            fut.add_done_callback(lambda _f: _apply())

    def _ensure_onec_dependencies(self):
        """Подготовка зависимостей удалёнки и отчёта в навигации"""
        if not getattr(self, "reportsbot", None):
            self.reportsbot = WialonReportsBot(self.driver_manager.driver, log_func=self.log)

        if not getattr(self, "rdp_activator", None):
            self.rdp_activator = lambda: True

        if not getattr(self, "onec_bot", None):
            self.onec_bot = OneCBot(rdp_activator=self.rdp_activator,
                                    reportsbot=self.reportsbot,
                                    log_func=self.log,)

    def _job_close_race(self, job_data: dict):
        obj = job_data["obj"]
        row = int(job_data["row"])

        race_no = job_data["race_no"]
        unit = job_data["unit"]
        load_zone = job_data["load_zone"]
        unload_zone = job_data["unload_zone"]

        if not race_no:
            raise ValueError("Пустой 'Рейс' в строке")
        if not unit:
            raise ValueError("Пустой 'ТС' в строке")
        if not load_zone:
            raise ValueError("Не определена geofence погрузки")
        if not unload_zone:
            raise ValueError("Не определена geofence выгрузки")

        ctx = RaceContext(
            race_name=race_no,
            race_search_text=race_no,
            meta={"row": row,
                  "unit": unit,
                  "load_zone": load_zone,
                  "unload_zone": unload_zone,
                  "saved_status_1c": obj.get("status_1c", ""),
                  "saved_status_text": obj.get("status_text", ""),
                  "saved_departure_dt_1c": obj.get("departure_dt_1c", ""),
                  "saved_onec_progress": obj.get("onec_progress", {}) or {},
                  "saved_wialon_payload": obj.get("wialon_payload", {}) or {}, }, )

        result = self.onec_bot.close_race(ctx)
        return ctx, result

    def _geofence_from_cell_text(self, s: str) -> str:
        s = (s or "").strip()
        if s.startswith("🏷"):
            first = s.splitlines()[0]
            return first.replace("🏷", "").strip()
        return ""