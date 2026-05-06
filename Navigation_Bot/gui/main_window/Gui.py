import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from PyQt6.QtWidgets import QApplication, QWidget
from Navigation_Bot.core.paths import INPUT_FILEPATH
from Navigation_Bot.core.paths import PIN_XLSX_FILEPATH, PIN_JSON_FILEPATH
from Navigation_Bot.gui.builders.main_ui_builder import MainUiBuilder
from Navigation_Bot.core.application.services.app_services import AppServices
from Navigation_Bot.gui.controllers.sheet_tabs_controller import SheetTabsController
from Navigation_Bot.gui.controllers.local_pages_controller import LocalPagesController
from Navigation_Bot.gui.settings.ui_bridge import UiBridge
from Navigation_Bot.gui.controllers.layout_controller import LayoutController
from Navigation_Bot.gui.settings.ui_settings import UiSettingsManager
from Navigation_Bot.gui.controllers.loading_overlay_controller import LoadingOverlayController
from Navigation_Bot.gui.controllers.dialog_request_controller import DialogRequestController
from Navigation_Bot.gui.controllers.main_actions_controller import MainActionsController
from Navigation_Bot.gui.controllers.startup_controller import StartupController


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.log = lambda msg: print(msg)
        self.INPUT_FILEPATH = INPUT_FILEPATH
        self.PIN_XLSX_FILEPATH = PIN_XLSX_FILEPATH
        self.PIN_JSON_FILEPATH = PIN_JSON_FILEPATH

        self.setWindowTitle("Navigation Manager")
        self.setMinimumSize(800, 600)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._single_row_processing = True
        self._log_enabled = True
        self._current_sort = None
        self.json_lock = Lock()

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
            if getattr(self, "row_highlighter", None):
                self.row_highlighter.apply_settings(self.ui_settings.data)
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

    def _get_sheet_json_path(self) -> str:
        """
        Возвращает путь к json для текущего листа Google Sheets.
        Например: config/selected_data_3_Kontrol_TS.json
        """
        base = Path(INPUT_FILEPATH)

        if not getattr(self, "gsheet", None) or not getattr(self.gsheet, "sheet", None):
            return str(base)

        index = getattr(self.gsheet, "worksheet_index", 0) or 0
        title = getattr(self.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"

        safe = re.sub(r"[^\w.-]+", "_", title, flags=re.UNICODE).strip("._-")
        if not safe:
            safe = f"sheet_{index}"

        filename = f"{base.stem}_{index}_{safe}.json"
        return str(base.with_name(filename))

    def _toggle_search_bar(self):
        if self.search_bar.isVisible():
            self.search_bar.hide()
        else:
            self.search_bar.start()

    def reload_and_show(self):
        with self.json_lock:
            self.task_repository.reload()
            self.json_data = self.task_repository.get()

        view_order = self.sort_controller.build_view_order()
        self.table_manager.display(view_order=view_order)
        self.row_highlighter.set_view_order(view_order)  # real_to_visual
        self.row_highlighter.highlight_expired_unloads()  # вызов красной подсветки

    def _on_header_clicked(self, logicalIndex: int):
        if logicalIndex == 0:  # 🔍 — открыть справочник ID
            self.actions.open_id_manager()
            return
        if logicalIndex == 2:
            self.sort_controller.current = None
            self.reload_and_show()
        elif logicalIndex == 8:
            self.sort_controller.current = "buffer"
            self.reload_and_show()
        elif logicalIndex == 7:
            self.sort_controller.current = "arrival"
            self.reload_and_show()
