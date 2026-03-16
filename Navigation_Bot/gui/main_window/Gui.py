import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QWidget)

from Navigation_Bot.core.paths import INPUT_FILEPATH
from Navigation_Bot.core.paths import PIN_XLSX_FILEPATH, PIN_JSON_FILEPATH
from Navigation_Bot.core.processedFlags import init_processed_flags
from Navigation_Bot.gui.builders.mainUiBuilder import MainUiBuilder
from Navigation_Bot.gui.controllers.appServices import AppServices
from Navigation_Bot.gui.controllers.sheetTabsController import SheetTabsController
from Navigation_Bot.gui.controllers.signalsBinder import SignalsBinder
from Navigation_Bot.gui.controllers.uiBridge import UiBridge
from Navigation_Bot.gui.controllers.windowLayoutManager import WindowLayoutManager
from Navigation_Bot.gui.dialogs.iDManagerDialog import IDManagerDialog
from Navigation_Bot.gui.dialogs.trackingIdEditor import TrackingIdEditor
from Navigation_Bot.gui.settings.uiSettings import UiSettingsManager


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.log = lambda msg: print(msg)
        self.INPUT_FILEPATH = INPUT_FILEPATH

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

        self.ui_bridge = UiBridge(self)
        self.ui_settings.apply_window(self)
        self.ui_settings.apply_table(self.table)

        self._layout_manager = WindowLayoutManager(titlebar_offset=30)
        self.browser_rect = self._layout_manager.apply_dual_screen_layout(self)

        self.local_page()
        self.init_managers()
        SignalsBinder(self).bind()

    def _open_wialon(self):
        self.show_loading("Запуск Wialon…")

        def job():
            try:
                self.processor.ensure_driver_and_bots()
                # ЛОГ будет через UiBridge внутри processor (после шага 1)
            except Exception as e:
                # тоже через мост
                if getattr(self, "ui_bridge", None):
                    self.ui_bridge.log.emit(f"❌ Ошибка запуска Wialon: {e}")
                else:
                    self.log(f"❌ Ошибка запуска Wialon: {e}")
            finally:

                QTimer.singleShot(0, self.hide_loading)

        self.executor.submit(job)

    def closeEvent(self, event):
        try:
            if getattr(self, "services", None):
                self.services.shutdown()
        except Exception as e:
            self.log(f"⚠️ Ошибка shutdown: {e}")

        super().closeEvent(event)

    def _startup_reload(self):
        try:
            if getattr(self, "sheet_tabs_controller", None):
                self.sheet_tabs_controller.activate_saved_tab()
        finally:
            self.hide_loading()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def show_loading(self, text="Загрузка…"):
        if getattr(self, "loading_label", None):
            self.loading_label.setText(text)

        if getattr(self, "loading_overlay", None):
            self.loading_overlay.setGeometry(self.table.geometry())
            self.loading_overlay.show()
            self.loading_overlay.raise_()

    def hide_loading(self):
        if getattr(self, "loading_overlay", None):
            self.loading_overlay.hide()

    # _____END

    def local_page(self):
        self.local_tabs = [{"kind": "local", "key": "local:pincodes", "title": "Пин коды"},
                           {"kind": "local", "key": "local:logistx", "title": "LogistX"},
                           ]
        self._local_pages_by_key = {}

        self.pincodes_xlsx_path = PIN_XLSX_FILEPATH
        self.pincodes_json_path = PIN_JSON_FILEPATH

    def init_managers(self):
        self.services = AppServices(self)
        self.services.build()

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

    def _load_from_google(self):
        """Загрузить задачи из текущего листа в свой json."""
        self._reload_after_gsheet = True

        try:
            json_path = self._get_sheet_json_path()
            self.data_context.set_filepath(json_path)

            self.gsheet.pull_to_context_async(
                data_context=self.data_context,
                input_filepath=json_path,
                executor=self.executor)
            # self.reload_and_show()

        except Exception as e:
            self.log(f'❌ Ошибка в NavigationGUI._load_from_google\n {e}')

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

        safe = re.sub(r"[^0-9A-Za-zА-Яа-я0-9]+", "_", title).strip("_")
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
            self.data_context.reload()
            self.json_data = self.data_context.get()
            init_processed_flags(self.json_data, self.json_data, loads_key="Выгрузка")
            self.data_context.save()

        view_order = self.sort_controller.build_view_order()
        self.table_manager.display(view_order=view_order)
        self.row_highlighter.set_view_order(view_order)  # real_to_visual
        self.row_highlighter.highlight_expired_unloads()  # вызов красной подсветки

    def _on_header_clicked(self, logicalIndex: int):
        if logicalIndex == 0:  # 🔍 — открыть справочник ID
            self.open_id_manager()
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

    def open_id_editor(self, row):
        car = self.json_data[row]
        dialog = TrackingIdEditor(car, log_func=self.log, parent=self)
        if dialog.exec():
            self.data_context.set(self.json_data)
            # self.table_manager.display()
            self.reload_and_show()

    def open_id_manager(self):
        dlg = IDManagerDialog(self)
        if dlg.exec():
            # self.table_manager.display()
            self.reload_and_show()
            self.log("✅ Id_car.json перезаписан")
