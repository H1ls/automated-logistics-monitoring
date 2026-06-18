from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtWidgets import QApplication, QWidget
from Navigation_Bot.core.paths import PIN_XLSX_FILEPATH, PIN_JSON_FILEPATH
from Navigation_Bot.gui.builders.main_ui_builder import MainUiBuilder
from Navigation_Bot.gui.app.app_services import AppServices
from Navigation_Bot.gui.controllers.sheet_tabs_controller import SheetTabsController
from Navigation_Bot.gui.controllers.local_pages_controller import LocalPagesController
from Navigation_Bot.gui.settings.ui_bridge import UiBridge
from Navigation_Bot.gui.controllers.layout_controller import LayoutController
from Navigation_Bot.gui.settings.ui_settings import UiSettingsManager
from Navigation_Bot.gui.controllers.loading_overlay_controller import LoadingOverlayController
from Navigation_Bot.gui.controllers.dialog_request_controller import DialogRequestController
from Navigation_Bot.gui.controllers.main_actions_controller import MainActionsController
from Navigation_Bot.gui.controllers.startup_controller import StartupController

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QStackedWidget, QTableWidget, QTextEdit

    from Navigation_Bot.bots.google_sheets_manager import GoogleSheetsManager
    from Navigation_Bot.core.NavigationProcessor.navigation_processor import NavigationProcessor
    from Navigation_Bot.core.application.services.editable_field_workflow_service import EditableFieldWorkflowService
    from Navigation_Bot.core.application.services.google.google_account_auth_service import GoogleAccountAuthService
    from Navigation_Bot.core.application.services.google.google_navigation_writer import GoogleNavigationWriter
    from Navigation_Bot.core.application.services.google.google_sync_service import GoogleSyncService
    from Navigation_Bot.core.application.services.new_task_workflow_service import NewTaskWorkflowService
    from Navigation_Bot.core.application.services.task_edit_service import TaskEditService
    from Navigation_Bot.core.application.services.tasks_service import TasksService
    from Navigation_Bot.core.hotkey_manager import HotkeyManager
    from Navigation_Bot.gui.app.app_context import AppContext
    from Navigation_Bot.gui.app.address_edit_workflow_service import AddressEditWorkflowService
    from Navigation_Bot.gui.controllers.log_controller import LogController
    from Navigation_Bot.gui.controllers.table_context_menu_controller import TableContextMenuController
    from Navigation_Bot.gui.dialogs.combined_settings_dialog import CombinedSettingsDialog
    from Navigation_Bot.gui.widgets.global_search_bar import GlobalSearchBar
    from Navigation_Bot.gui.widgets.row_high_lighter import RowHighlighter
    from Navigation_Bot.gui.widgets.smooth_scroll import SmoothScrollController
    from Navigation_Bot.gui.widgets.table.table_manager import TableManager
    from Navigation_Bot.gui.widgets.table_sort_controller import TableSortController


class NavigationGUI(QWidget):
    log: Callable[[str], None]
    log_info: Callable[[str], None]
    log_success: Callable[[str], None]
    log_warning: Callable[[str], None]
    log_error: Callable[[str], None]

    btn_load_google: QPushButton
    btn_create_race: QPushButton
    btn_process_all: QPushButton
    btn_refresh_table: QPushButton
    btn_wialon: QPushButton
    btn_settings: QPushButton
    btn_navigation_history: QPushButton
    btn_clear_log: QPushButton

    table: QTableWidget
    smooth_scroll: SmoothScrollController
    log_box: QTextEdit
    logger: LogController
    search_bar: GlobalSearchBar
    stack: QStackedWidget
    page_gsheet: QWidget
    loading_overlay: QWidget
    loading_card: QWidget
    loading_label: QLabel
    loading_bar: QProgressBar
    sheet_tabs_layout: QHBoxLayout

    services: AppServices
    ctx: AppContext
    loading: LoadingOverlayController
    layout_controller: LayoutController
    local_pages_controller: LocalPagesController
    dialog_requests: DialogRequestController
    actions: MainActionsController
    startup_controller: StartupController
    sheet_tabs_controller: SheetTabsController

    api_client: Any
    vehicle_repository: Any
    task_repository: Any
    settings_controller: Any
    settings_ui: CombinedSettingsDialog
    gsheet: GoogleSheetsManager
    google_navigation_writer: GoogleNavigationWriter
    google_account_auth_service: GoogleAccountAuthService
    task_edit_service: TaskEditService
    status_event_service: Any
    tasks_service: TasksService
    google_sync_service: GoogleSyncService
    navigation_history_service: Any
    route_estimate_history_service: Any
    note_history_service: Any
    new_task_workflow_service: NewTaskWorkflowService
    editable_field_workflow_service: EditableFieldWorkflowService
    address_edit_workflow_service: AddressEditWorkflowService
    table_manager: TableManager
    row_highlighter: RowHighlighter
    processor: NavigationProcessor
    sort_controller: TableSortController
    hotkeys: HotkeyManager
    table_context_menu: TableContextMenuController

    task_rows: list[dict[str, Any]]
    browser_rect: Any
    ui_bridge: UiBridge

    def __init__(self):
        super().__init__()

        self.log = lambda msg: print(msg)
        self.PIN_XLSX_FILEPATH = PIN_XLSX_FILEPATH
        self.PIN_JSON_FILEPATH = PIN_JSON_FILEPATH

        self.setWindowTitle("Navigation Manager")
        self.setMinimumSize(800, 600)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._single_row_processing = True
        self._log_enabled = True
        self._current_sort = None
        self._last_reload_signature = None
        self._last_reload_at = 0.0
        self.task_data_lock = Lock()

        self._row_highlight_until = {}  # {row_idx: datetime_until}
        self.updated_rows = []

        self.ui_settings = UiSettingsManager(log_func=self.log)
        self.init_ui()

        self.loading = LoadingOverlayController(self)
        self.show()
        self.loading.show("Инициализация приложения…", "Подготовка интерфейса")

        QApplication.processEvents()
        self.ui_bridge = UiBridge(self)
        self.ui_settings.apply_window(self)
        self.ui_settings.apply_table(self.table)

        # Читаем режим размещения и выбор монитора из настроек
        self.layout_controller = LayoutController(self)
        self.layout_controller.setup()

        self.local_pages_controller = LocalPagesController(self)
        self.dialog_requests = DialogRequestController(self)
        self.actions = MainActionsController(self)
        self.startup_controller = StartupController(self)
        self.startup_controller.start()

    def closeEvent(self, event):
        """Гарантированная очистка при закрытии окна"""
        try:
            if getattr(self, "dialog_requests", None):
                self.dialog_requests.stop()

            processor = getattr(self, "processor", None)
            browser_session = getattr(processor, "browser_session", None) if processor else None
            if browser_session:
                try:
                    browser_session.stop()
                except Exception as e:
                    self.log(f"⚠️ Ошибка закрытия браузера: {e}")

            if getattr(self, "services", None):
                self.services.shutdown()
        except Exception as e:
            self.log(f"⚠️ Ошибка shutdown: {e}")
        finally:
            if getattr(self, "executor", None):
                try:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self.executor.shutdown(wait=False)
                except Exception as e:
                    self.log(f"⚠️ Ошибка остановки executor: {e}")

            super().closeEvent(event)

    def resizeEvent(self, event):
        """Обновить позицию splash screen когда окно меняет размер."""
        super().resizeEvent(event)
        if getattr(self, "loading", None):
            self.loading.reposition()

    def hide_loading(self):
        if getattr(self, "loading", None):
            self.loading.hide()

    def get_or_create_local_page(self, key: str):
        if not getattr(self, "local_pages_controller", None):
            return None
        return self.local_pages_controller.get_or_create_page(key)

    def _apply_runtime_settings(self):
        try:
            if getattr(self, "logger", None):
                log_cfg = self.ui_settings.data.get("log", {}) or {}
                self.logger.set_audience(log_cfg.get("audience", "user"))
            if getattr(self, "row_highlighter", None):
                self.row_highlighter.apply_settings(self.ui_settings.data)
            if getattr(self, "table_manager", None):
                self.table_manager.apply_settings(self.ui_settings.data)
        except Exception as e:
            self.log(f"⚠️ Не удалось применить runtime-настройки: {e}")

    def init_managers(self):
        self.services = AppServices(self)
        self.services.build()

        self._apply_runtime_settings()

        self.sheet_tabs_controller = SheetTabsController(gui=self)
        self.sheet_tabs_controller.build()

    def init_ui(self):
        MainUiBuilder().build(self)

        # apply_table/resize callbacks должны вешаться ПОСЛЕ создания table
        hdr_h = self.table.horizontalHeader()
        hdr_v = self.table.verticalHeader()
        hdr_h.sectionResized.connect(
            lambda logical, old, new: self.ui_settings.on_col_resized(logical, old, new, self.table))
        hdr_v.sectionResized.connect(
            lambda logical, old, new: self.ui_settings.on_row_resized(logical, old, new, self.table))

    def _get_sheet_source_key(self) -> str:
        """
        Возвращает ключ источника для текущего листа Google Sheets.
        Ключ нужен для разделения листов Google Sheets в PostgreSQL/API.
        """
        if not getattr(self, "gsheet", None) or not getattr(self.gsheet, "sheet", None):
            return "default"

        index = getattr(self.gsheet, "worksheet_index", 0) or 0
        title = getattr(self.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"
        return f"sheet_{index}_{title}"

    def _toggle_search_bar(self):
        if self.search_bar.isVisible():
            self.search_bar.hide()
        else:
            self.search_bar.start()

    def reload_and_show(self):
        with self.task_data_lock:
            source_key = getattr(self.task_repository, "current_source_key", "")
            use_incremental = self._use_incremental_refresh()
            signature = (source_key, use_incremental)
            now = time.monotonic()
            if use_incremental and self._last_reload_signature == signature and now - self._last_reload_at < 0.25:
                return
            self._last_reload_signature = signature
            self._last_reload_at = now

            if use_incremental:
                self.task_repository.refresh_incremental_or_reload()
            else:
                self.task_repository.reload()
            self.task_rows = self.task_repository.get()

        self.display_current_data()

    def display_current_data(self):
        with self.task_data_lock:
            self.task_rows = self.task_repository.get()

        view_order = self.sort_controller.build_view_order()
        self.table_manager.display(reload_from_file=False, view_order=view_order)
        self.row_highlighter.set_view_order(view_order)  # real_to_visual
        self.row_highlighter.highlight_expired_unloads()
        self.row_highlighter.reapply_from_rows()

    @staticmethod
    def _use_incremental_refresh() -> bool:
        return os.getenv("NAV_API_INCREMENTAL_REFRESH", "").strip().lower() in {"1", "true", "yes", "on"}

    def _on_header_clicked(self, logical_index: int):
        if logical_index == 0:  # 🔍 — открыть справочник ID
            self.actions.open_id_manager()
            return
        if logical_index == 2:
            self.sort_controller.current = None
            self.reload_and_show()
        elif logical_index == 8:
            self.sort_controller.current = "buffer"
            self.reload_and_show()
        elif logical_index == 7:
            self.sort_controller.current = "arrival"
            self.reload_and_show()
