from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from PyQt6.QtWidgets import QApplication, QWidget
from Navigation_Bot.core.paths import PIN_XLSX_FILEPATH, PIN_JSON_FILEPATH
from Navigation_Bot.gui.builders.main_ui_builder import MainUi, MainUiBuilder
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
from Navigation_Bot.gui.app.app_context import AppContext


class NavigationGUI(QWidget):
    log: Callable[[str], None]
    log_info: Callable[[str], None]
    log_success: Callable[[str], None]
    log_warning: Callable[[str], None]
    log_error: Callable[[str], None]

    ui: MainUi
    services: AppServices
    ctx: AppContext
    loading: LoadingOverlayController
    layout_controller: LayoutController
    local_pages_controller: LocalPagesController
    dialog_requests: DialogRequestController
    actions: MainActionsController
    startup_controller: StartupController
    sheet_tabs_controller: SheetTabsController
    task_rows: list[dict[str, Any]]
    browser_rect: Any
    ui_bridge: UiBridge

    def __getattr__(self, name: str):
        """Мост совместимости на время миграции контроллеров на ui/ctx."""
        try:
            ui = object.__getattribute__(self, "ui")
        except AttributeError:
            ui = None
        if ui is not None and hasattr(ui, name):
            return getattr(ui, name)

        try:
            ctx = object.__getattribute__(self, "ctx")
        except AttributeError:
            ctx = None
        if ctx is not None and hasattr(ctx, name):
            return getattr(ctx, name)

        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    def __init__(self, api_key: str = ""):
        super().__init__()

        self.log = lambda msg: print(msg)
        self.session_api_key = api_key
        self.PIN_XLSX_FILEPATH = PIN_XLSX_FILEPATH
        self.PIN_JSON_FILEPATH = PIN_JSON_FILEPATH

        self.setWindowTitle("Navigation Manager")
        self.setMinimumSize(800, 600)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._single_row_processing = True
        self._log_enabled = True
        self._current_sort = None
        self._row_highlight_until = {}  # {row_idx: datetime_until}
        self.updated_rows = []
        self.task_rows = []

        self.ui_settings = UiSettingsManager(log_func=self.log)
        self.init_ui()

        self.loading = LoadingOverlayController(self)
        self.show()
        self.loading.show("Инициализация приложения…", "Подготовка интерфейса")

        QApplication.processEvents()
        self.ui_bridge = UiBridge(self)
        self.ui_settings.apply_window(self)
        self.ui_settings.apply_table(self.ui.table)

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

            processor = self.ctx.processor if hasattr(self, "ctx") and hasattr(self.ctx, "processor") else None
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
            if hasattr(self, "ui"):
                log_cfg = self.ui_settings.data.get("log", {}) or {}
                self.ui.logger.set_audience(log_cfg.get("audience", "user"))
            if hasattr(self, "ctx") and hasattr(self.ctx, "row_highlighter"):
                self.ctx.row_highlighter.apply_settings(self.ui_settings.data)
            if hasattr(self, "ctx") and hasattr(self.ctx, "table_manager"):
                self.ctx.table_manager.apply_settings(self.ui_settings.data)
        except Exception as e:
            self.log(f"⚠️ Не удалось применить runtime-настройки: {e}")

    def init_managers(self):
        self.ctx = AppContext()
        self.ctx.ui_bridge = self.ui_bridge
        self.services = AppServices(self)
        self.services.build()

        self._apply_runtime_settings()

        self.sheet_tabs_controller = SheetTabsController(gui=self)
        self.sheet_tabs_controller.build()

    def init_ui(self):
        self.ui = MainUiBuilder().build(
            self,
            ui_settings=self.ui_settings,
            log_enabled_getter=lambda: self._log_enabled,
            on_header_clicked=self._on_header_clicked,
        )

        self.log = self.ui.logger.log
        self.log_info = self.ui.logger.info
        self.log_success = self.ui.logger.success
        self.log_warning = self.ui.logger.warning
        self.log_error = self.ui.logger.error

        # apply_table/resize callbacks должны вешаться ПОСЛЕ создания table
        hdr_h = self.ui.table.horizontalHeader()
        hdr_v = self.ui.table.verticalHeader()
        hdr_h.sectionResized.connect(
            lambda logical, old, new: self.ui_settings.on_col_resized(logical, old, new, self.ui.table))
        hdr_v.sectionResized.connect(
            lambda logical, old, new: self.ui_settings.on_row_resized(logical, old, new, self.ui.table))

    def _get_sheet_source_key(self) -> str:
        """
        Возвращает ключ источника для текущего листа Google Sheets.
        Ключ нужен для разделения листов Google Sheets в PostgreSQL/API.
        """
        if not hasattr(self, "ctx") or not hasattr(self.ctx, "gsheet") or not getattr(self.ctx.gsheet, "sheet", None):
            return "default"

        index = getattr(self.ctx.gsheet, "worksheet_index", 0) or 0
        title = getattr(self.ctx.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"
        return f"sheet_{index}_{title}"

    def _toggle_search_bar(self):
        if self.ui.search_bar.isVisible():
            self.ui.search_bar.hide()
        else:
            self.ui.search_bar.start()

    def reload_and_show(self):
        self.ctx.task_table_controller.reload_and_show()

    def display_current_data(self):
        self.ctx.task_table_controller.display_current_data()

    def _on_header_clicked(self, logical_index: int):
        controller = self.ctx.task_table_controller if hasattr(self, "ctx") and hasattr(self.ctx, "task_table_controller") else None
        if controller is not None:
            controller.on_header_clicked(logical_index)
