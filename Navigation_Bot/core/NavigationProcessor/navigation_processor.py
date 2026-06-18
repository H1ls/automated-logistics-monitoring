import traceback
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from Navigation_Bot.core.NavigationProcessor.batch_processing_service import BatchProcessingService
from Navigation_Bot.core.NavigationProcessor.browser_session import BrowserSession
from Navigation_Bot.core.NavigationProcessor.logistx_race_service import LogistxRaceService
from Navigation_Bot.core.application.services.navigation_row_service import NavigationRowService
                                                                                                   

class NavigationProcessor:
    DEFAULT_TIMEOUT_SECONDS = 3

    def __init__(self, task_repository, logger, gsheet, display_callback, single_row, updated_rows,
                 executor=None, highlight_callback=None, browser_rect=None, ui_bridge=None, tasks_service=None,
                 navigation_history_service=None, route_estimate_history_service=None,
                 pause_dialog_factory=None, gui_parent=None, timeout_seconds=None):

        self.task_repository = task_repository
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
        self._batch_pause_requested = False  # флаг для остановки batch после паузы
        self._batch_progress = {}  # {session_id: {"processed": int, "total": int, "remaining_rows": list}}

        self.ui_bridge = ui_bridge
        self.tasks_service = tasks_service
        self.navigation_history_service = navigation_history_service
        self.route_estimate_history_service = route_estimate_history_service
        self.pause_dialog_factory = pause_dialog_factory  # фабрика диалога паузы
        self.gui_parent = gui_parent  # родительское окно GUI для показа диалогов
        self.timeout_seconds = self._normalize_timeout(timeout_seconds)

        self.browser_session = BrowserSession(logger=self.log,
                                              browser_rect=self.browser_rect,
                                              ui_bridge=self.ui_bridge, )

        self.row_service = NavigationRowService(logger=self.log,
                                                gsheet=self.gsheet,
                                                tasks_service=self.tasks_service,
                                                ui_bridge=self.ui_bridge,
                                                display_callback=self.display_callback,
                                                single_row_processing=self._single_row_processing,
                                                updated_rows=self.updated_rows,
                                                navigation_history_service=self.navigation_history_service,
                                                route_estimate_history_service=self.route_estimate_history_service,
                                                )

        self.logistx_race_service = LogistxRaceService(logger=self.log,
                                                       executor=self.executor,
                                                       browser_session=self.browser_session,
                                                       ui_bridge=self.ui_bridge, )
        # TODO: Изменить вызов
        self.batch_processing_service = BatchProcessingService(self)
        self._dialog_request_queue = self.batch_processing_service._dialog_request_queue
        self._dialog_result_queue = self.batch_processing_service._dialog_result_queue

    @classmethod
    def _normalize_timeout(cls, value) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            timeout = cls.DEFAULT_TIMEOUT_SECONDS
        return max(0, timeout)

    def set_timeout_seconds(self, value) -> None:
        self.timeout_seconds = self._normalize_timeout(value)

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

    def _get_row_identity_by_row(self, row_idx: int) -> int | None:
        if not self.tasks_service:
            return None
        return self.tasks_service.get_row_identity_by_row(row_idx)

    def _get_processible_rows(self) -> list[tuple[int, int | None]]:
        if not self.tasks_service:
            return []
        return self.tasks_service.get_processible_rows()

    def _set_row_busy(self, row_identity: int | None, value: bool) -> None:
        if self.ui_bridge and row_identity is not None:
            self.ui_bridge.set_busy.emit(row_identity, value)

    def _highlight_row(self, row_idx: int, row_identity: int | None) -> None:
        if not self.highlight_cb:
            return

        try:
            if row_identity is None:
                self.log(f"⚠️ Нет row_identity у строки {row_idx}. Подсветка пропущена.")
                return
            self.highlight_cb(row_identity)

            # В batch-режиме GUI не перерисовывается после каждой строки, а некоторые операции UI
            # (например, изменение busy-state) могут сбрасывать фон отдельных ячеек.
            # Поэтому сразу после сохранения highlight_until пере-применяем подсветки из JSON.
            if self.ui_bridge and getattr(self.ui_bridge, "gui", None):
                gui = self.ui_bridge.gui
                rh = getattr(gui, "row_highlighter", None)
                if rh:
                    self.ui_bridge.call.emit(lambda: rh.reapply_from_rows())
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

        row_identity = self._get_row_identity_by_row(row_idx)

        try:
            self._set_row_busy(row_identity, True)
            self._highlight_row(row_idx, row_identity)
            future = self.executor.submit(self.process_row_wrapper, row_idx, row_identity)
        except Exception as e:
            self.log(f"❌ Не удалось запустить обработку строки {row_idx}: {e}")
            self.log(traceback.format_exc())
            self._leave_processing("single")
            self._set_row_busy(row_identity, False)
            return

        future.add_done_callback(lambda f: self._on_single_row_future_done(f, row_idx, row_identity))

    def _on_single_row_future_done(self, future: Future, row_idx: int, fallback_row_identity: int | None) -> None:
        row_identity = fallback_row_identity

        try:
            success, error_msg, returned_row_identity = future.result()
            if returned_row_identity is not None:
                row_identity = returned_row_identity

            if success:
                pass
                # self.log(f"✅ Обработка строки {row_idx} завершилась")
            else:
                self.log(f"❌ Обработка строки {row_idx} завершилась с ошибкой: {error_msg}")

        except Exception as e:
            self.log(f"❌ process_row_wrapper упал без штатного результата: строка {row_idx}: {e}")
            self.log(traceback.format_exc())

        finally:
            self._leave_processing("single")
            self._set_row_busy(fallback_row_identity, False)
            if row_identity != fallback_row_identity:
                self._set_row_busy(row_identity, False)

    def process_row_wrapper(self, row: int, fallback_row_identity: int | None = None): 
        
        """
        Обработать строку и вернуть результат (успех, сообщение об ошибке)
        """
        row_identity = fallback_row_identity

        try:
            self.browser_session.ensure_ready()

            _, returned_row_identity = self.row_service.process_row(row,
                                                                 navibot=self.browser_session.navibot,
                                                                 mapsbot=self.browser_session.mapsbot,
                                                                 switch_tab=self.browser_session.switch_tab_or_log, )

            if returned_row_identity is not None:
                row_identity = returned_row_identity

            return True, "", row_identity  # успех

        except Exception as e:
            error_msg = str(e)
            self.log(f"❌ Ошибка в process_row_wrapper: {error_msg}")
            self.log(traceback.format_exc())
            return False, error_msg, row_identity

    def process_all(self):
        self.batch_processing_service.process_all()

    def process_pending_dialog_requests(self):
        self.batch_processing_service.process_pending_dialog_requests()

    def resume_batch_processing(self):
        self.batch_processing_service.resume_batch_processing()
