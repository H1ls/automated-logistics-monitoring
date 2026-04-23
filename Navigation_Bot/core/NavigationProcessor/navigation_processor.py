import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from Navigation_Bot.core.NavigationProcessor.browser_session import BrowserSession
from Navigation_Bot.core.NavigationProcessor.logistx_race_service import LogistxRaceService
from Navigation_Bot.core.NavigationProcessor.navigation_row_service import NavigationRowService


class NavigationProcessor:
    def __init__(self, data_context, logger, gsheet, display_callback, single_row, updated_rows,
                 executor=None, highlight_callback=None, browser_rect=None, ui_bridge=None, tasks_service=None, ):

        self.data_context = data_context
        self.log = logger
        self.gsheet = gsheet
        self.display_callback = display_callback
        self._single_row_processing = single_row
        self.updated_rows = updated_rows if updated_rows is not None else []

        self.browser_rect = browser_rect
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.highlight_cb = highlight_callback

        self._processing_lock = Lock()
        self._processing_mode = None  # None / single / batch

        self.ui_bridge = ui_bridge
        self.tasks_service = tasks_service

        self.browser_session = BrowserSession(logger=self.log,
                                              browser_rect=self.browser_rect,
                                              ui_bridge=self.ui_bridge, )

        self.row_service = NavigationRowService(data_context=self.data_context,
                                                logger=self.log,
                                                gsheet=self.gsheet,
                                                tasks_service=self.tasks_service,
                                                ui_bridge=self.ui_bridge,
                                                display_callback=self.display_callback,
                                                single_row_processing=self._single_row_processing,
                                                updated_rows=self.updated_rows, )

        self.logistx_race_service = LogistxRaceService(logger=self.log,
                                                       executor=self.executor,
                                                       browser_session=self.browser_session,
                                                       ui_bridge=self.ui_bridge, )

    # Processing mode
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

    # Обновлен буфер строк
    def _clear_updated_rows(self) -> None:
        self.updated_rows.clear()

    def _flush_updated_rows_to_google(self) -> None:
        if self.updated_rows:
            self.gsheet.write_all(self.updated_rows)
            self.updated_rows.clear()

    # Хелпер для строк
    def _row_exists(self, row_idx: int) -> bool:
        if not self.tasks_service:
            return False
        return self.tasks_service.exists_row(row_idx)

    def _get_index_key_by_row(self, row_idx: int) -> int | None:
        if not self.tasks_service:
            return None
        return self.tasks_service.get_index_key_by_row(row_idx)

    def _get_processible_rows(self) -> list[tuple[int, int | None]]:
        if not self.tasks_service:
            return []
        return self.tasks_service.get_processible_rows()

    def _set_row_busy(self, index_key: int | None, value: bool) -> None:
        if self.ui_bridge and index_key is not None:
            self.ui_bridge.set_busy.emit(index_key, value)

    def _highlight_row(self, row_idx: int, index_key: int | None) -> None:
        if not self.highlight_cb:
            return

        try:
            if index_key is None:
                self.log(f"⚠️ Нет поля 'index' у строки {row_idx}. Подсветка пропущена.")
                return
            self.highlight_cb(index_key)
        except Exception as e:
            self.log(f"⚠️ Ошибка подсветки строки {row_idx}: {e}")

    def _refresh_ui(self) -> None:
        if self.ui_bridge:
            self.ui_bridge.refresh.emit()
        else:
            self.display_callback()

    # Запуск для одной строки
    def on_row_click(self, row_idx: int):
        if not self._try_enter_single_processing():
            self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return

        if not self._row_exists(row_idx):
            self._leave_processing("single")
            self.log(f"⚠️ Строка {row_idx} больше не существует. Пропуск.")
            return

        index_key = self._get_index_key_by_row(row_idx)

        self._set_row_busy(index_key, True)
        self._highlight_row(row_idx, index_key)

        self.executor.submit(self.process_row_wrapper, row_idx, index_key)

    def process_row_wrapper(self, row: int, fallback_index_key: int | None = None):
        index_key = fallback_index_key

        try:
            self.browser_session.ensure_ready()

            _, returned_index_key = self.row_service.process_row(row,
                                                                 navibot=self.browser_session.navibot,
                                                                 mapsbot=self.browser_session.mapsbot,
                                                                 switch_tab=self.browser_session.switch_tab_or_log, )

            if returned_index_key is not None:
                index_key = returned_index_key

        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")
            self.log(traceback.format_exc())

        finally:
            with self._processing_lock:
                is_single_mode = self._processing_mode == "single"

            if is_single_mode:
                self._leave_processing("single")

            self._set_row_busy(index_key, False)

    # Batch
    def _prepare_batch_processing(self) -> tuple[bool, list[tuple[int, int | None]], bool]:
        if not self._try_enter_batch_processing():
            self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return False, [], False

        prev_single_mode = self._single_row_processing
        self._single_row_processing = False
        self.row_service.set_single_row_processing(False)

        self._clear_updated_rows()
        self.log("▶ Обработка всех ТС...")

        rows_with_keys = self._get_processible_rows()
        return True, rows_with_keys, prev_single_mode

    def _run_batch_rows(self, rows_with_keys: list[tuple[int, int | None]]) -> int:
        futures = []

        for row, index_key in rows_with_keys:
            future = self.executor.submit(self.process_row_wrapper, row, index_key)
            futures.append(future)

        for f in futures:
            f.result()

        return len(futures)

    def _finalize_batch_processing(self, prev_single_mode: bool, processed_count: int) -> None:
        self._leave_processing("batch")
        self._single_row_processing = prev_single_mode
        self.row_service.set_single_row_processing(prev_single_mode)

        self._refresh_ui()
        self.log(f"✅ Обработка всех ТС завершена ({processed_count} строк)")

    # TODO: Проход по каждой, с остановкой на права выбора "Продолжить/Нет" + Таймер
    def process_all(self):
        ok, rows_with_keys, prev_single_mode = self._prepare_batch_processing()
        if not ok:
            return

        if not rows_with_keys:
            self._single_row_processing = prev_single_mode
            self.row_service.set_single_row_processing(prev_single_mode)
            self._leave_processing("batch")
            self._refresh_ui()
            self.log("ℹ️ Нет строк для обработки.")
            return

        def _run_batch():
            processed_count = 0
            try:
                processed_count = self._run_batch_rows(rows_with_keys)
            except Exception as e:
                self.log(f"❌ Ошибка batch-обработки: {e}")
                self.log(traceback.format_exc())
            finally:
                self._finalize_batch_processing(prev_single_mode, processed_count)

        threading.Thread(target=_run_batch, daemon=True).start()

    # TODO: что то сделать с полным пакетом данных для отправки в goggle, сейчас по штучно
    def write_all_to_google(self):
        self._flush_updated_rows_to_google()
