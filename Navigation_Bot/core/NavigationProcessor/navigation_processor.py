# Navigation_Bot\core\navigation_processor.py
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from Navigation_Bot.core.NavigationProcessor.navigation_row_service import NavigationRowService
from Navigation_Bot.core.NavigationProcessor.browser_session import BrowserSession
from Navigation_Bot.core.NavigationProcessor.logistx_race_service import LogistxRaceService


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

        self._processing_lock = Lock()
        self._processing_mode = None  # None/single/batch
        self.ui_bridge = ui_bridge

        self.browser_session = BrowserSession(logger=self.log, browser_rect=self.browser_rect, ui_bridge=self.ui_bridge,
                                              )
        self.row_service = NavigationRowService(data_context=self.data_context,
                                                logger=self.log,
                                                gsheet=self.gsheet,
                                                ui_bridge=self.ui_bridge,
                                                display_callback=self.display_callback,
                                                single_row_processing=self._single_row_processing,
                                                updated_rows=self.updated_rows,
                                                )
        self.logistx_race_service = LogistxRaceService(logger=self.log,
                                                       executor=self.executor,
                                                       browser_session=self.browser_session,
                                                       ui_bridge=self.ui_bridge,
                                                       )

    def _try_enter_single_processing(self) -> bool:
        with self._processing_lock:
            if self._processing_mode is not None:
                return False
            self._processing_mode = "single"
            return True

    def _try_enter_batch_processing(self) -> bool:
        with self._processing_lock:
            if self._processing_mode is not None:
                return False
            self._processing_mode = "batch"
            return True

    def _leave_processing(self, expected_mode: str | None = None) -> None:
        with self._processing_lock:
            if expected_mode is None or self._processing_mode == expected_mode:
                self._processing_mode = None

    def on_row_click(self, row_idx: int):

        if not self._try_enter_single_processing():
            if self.log:
                self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return
        data = self.data_context.get() or []
        if not (0 <= row_idx < len(data)):
            self._leave_processing("single")
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
            self.browser_session.ensure_ready()

            _, index_key = self.row_service.process_row(row,
                                                        navibot=self.browser_session.navibot,
                                                        mapsbot=self.browser_session.mapsbot,
                                                        switch_tab=self.browser_session.switch_tab_or_log, )

        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")
            self.log(traceback.format_exc())
        finally:
            with self._processing_lock:
                is_single_mode = self._processing_mode == "single"

            if is_single_mode:
                self._leave_processing("single")

            if self.ui_bridge and index_key is not None:
                self.ui_bridge.set_busy.emit(index_key, False)

    def process_all(self):

        # Не стартуем второй batch/single во время текущей обработки
        if not self._try_enter_batch_processing():
            self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return
        prev_single_mode = self._single_row_processing
        self._single_row_processing = False
        self.row_service.set_single_row_processing(False)
        self.updated_rows = []
        self.log("▶ Обработка всех ТС...")

        data = self.data_context.get() or []
        rows = [i for i, car in enumerate(data)
                if isinstance(car, dict) and car.get("id") and car.get("ТС")]

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
                self._leave_processing("batch")
                self._single_row_processing = prev_single_mode
                self.row_service.set_single_row_processing(prev_single_mode)
                if self.ui_bridge:
                    self.ui_bridge.refresh.emit()
                else:
                    self.display_callback()
                self.log("✅ Обработка всех ТС завершена")

        threading.Thread(target=_run_batch, daemon=True).start()

    # TODO: что то сделать с полным пакетом данных для отправки в goggle, сейчас по штучно
    def write_all_to_google(self):
        if self.updated_rows:
            self.gsheet.write_all(self.updated_rows)
            self.updated_rows = []
