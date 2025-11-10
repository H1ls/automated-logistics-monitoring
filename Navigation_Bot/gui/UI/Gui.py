from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QTextEdit,
                             QLabel, QHeaderView, QAbstractItemView, QMessageBox, QTableWidgetItem)
from PyQt6.QtGui import QShortcut, QKeySequence

from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager

from Navigation_Bot.core.navigationProcessor import NavigationProcessor
from Navigation_Bot.core.paths import INPUT_FILEPATH
from Navigation_Bot.core.processedFlags import init_processed_flags
from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.hotkeyManager import HotkeyManager

from Navigation_Bot.gui.combinedSettingsDialog import CombinedSettingsDialog
from Navigation_Bot.gui.trackingIdEditor import TrackingIdEditor
from Navigation_Bot.gui.tableManager import TableManager
from Navigation_Bot.gui.iDManagerDialog import IDManagerDialog

from Navigation_Bot.gui.UI.tableSortController import TableSortController
from Navigation_Bot.gui.UI.rowHighlighter import RowHighlighter


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Navigation Manager")
        self.resize(1050, 1033)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._single_row_processing = True
        self._log_enabled = True
        self._current_sort = None
        self.json_lock = Lock()

        self._row_highlight_until = {}  # {row_idx: datetime_until}

        self.updated_rows = []

        self.init_ui()
        self.init_managers()
        self.connect_signals()

        self.table_manager.display()

    def init_managers(self):
        self.data_context = DataContext(str(INPUT_FILEPATH),
                                        log_func=self.log)
        self.json_data = self.data_context.get()  # для обратной совместимости
        self.hotkeys = HotkeyManager(log_func=self.log)
        self.settings_ui = CombinedSettingsDialog(self)

        self.gsheet = GoogleSheetsManager(log_func=self.log)
        self.table_manager = TableManager(table_widget=self.table,
                                          data_context=self.data_context,
                                          log_func=self.log,
                                          on_row_click=None,
                                          on_edit_id_click=self.open_id_editor,
                                          gsheet=self.gsheet)
        self.row_highlighter = RowHighlighter(table=self.table,
                                              data_context=self.data_context,
                                              log=self.log,
                                              hours_default=2)
        self.processor = NavigationProcessor(data_context=self.data_context,
                                             logger=self.log,
                                             gsheet=self.gsheet,
                                             filepath=str(INPUT_FILEPATH),
                                             display_callback=self.reload_and_show,
                                             single_row=self._single_row_processing,
                                             updated_rows=self.updated_rows,
                                             executor=self.executor,
                                             highlight_callback=self.row_highlighter.highlight_for
                                             )
        self.sort_controller = TableSortController(data_context=self.data_context,
                                                   table_manager=self.table_manager,
                                                   log=self.log)

        self.table_manager.on_row_click = self.processor.on_row_click
        self.table_manager.after_display = self.row_highlighter.reapply_from_json

    def init_ui(self):
        layout = QVBoxLayout()
        top = QHBoxLayout()

        # Верхние кнопки
        self.btn_load_google = QPushButton("Загрузить Задачи")
        self.btn_process_all = QPushButton("▶ Пробежать все ТС")
        self.btn_clear_json = QPushButton("🗑 Очистить JSON")
        self.btn_refresh_table = QPushButton("🔄 Обновить")
        self.btn_settings = QPushButton("Настройки ⚙️")

        for btn in [
            self.btn_load_google,
            self.btn_process_all,
            self.btn_clear_json,
            self.btn_refresh_table,
            self.btn_settings
        ]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(130)

        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_process_all)
        top.addWidget(self.btn_refresh_table)
        top.addWidget(self.btn_clear_json)
        top.addWidget(self.btn_settings)
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "КА", "Погрузка", "Выгрузка", "гео", "Время прибытия", "Запас"])
        self.table.setHorizontalHeaderItem(0, QTableWidgetItem("🔍"))
        hdr = self.table.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(self._on_header_clicked)

        self.table.setWordWrap(True)
        self.table.setColumnWidth(0, 40)  #
        self.table.setColumnWidth(1, 40)  # id
        self.table.setColumnWidth(2, 82)  # ТС
        self.table.setColumnWidth(3, 30)  # КА
        self.table.setColumnWidth(4, 270)  # Погрузка
        self.table.setColumnWidth(5, 275)  # Выгрузка
        self.table.setColumnWidth(6, 168)  # гео
        self.table.setColumnWidth(7, 65)  # Время прибытия
        self.table.setColumnWidth(8, 60)  # Запас
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setColumnHidden(1, True)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(150)

        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Лог:"))
        layout.addWidget(self.log_box)

        self.setLayout(layout)

    def connect_signals(self):
        self.table.cellDoubleClicked.connect(self.table_manager.edit_cell_content)

        self.settings_ui.settings_changed.connect(self._on_settings_changed)
        self.btn_settings.clicked.connect(lambda: self.settings_ui.exec())

        self.btn_process_all.clicked.connect(self.processor.process_all)
        self.btn_refresh_table.clicked.connect(self.table_manager.display)
        self.table.itemChanged.connect(self.table_manager.save_to_json_on_edit)
        self.btn_clear_json.clicked.connect(self.confirm_clear_json)
        self.btn_load_google.clicked.connect(lambda: self.gsheet.pull_to_context_async(data_context=self.data_context,
                                                                                       input_filepath=str(
                                                                                           INPUT_FILEPATH),
                                                                                       executor=self.executor))
        QShortcut(QKeySequence("F11"), self).activated.connect(self.hotkeys.start)
        QShortcut(QKeySequence("F12"), self).activated.connect(self.hotkeys.stop)

    def _on_settings_changed(self, sections: set):
        if "google_config" in sections:
            self.gsheet = GoogleSheetsManager(log_func=self.log)
            self.log("🔁 GoogleSheetsManager пересоздан по новым настройкам")

        driver = getattr(getattr(self, "processor", None), "driver_manager", None)
        driver = getattr(driver, "driver", None)

        if "wialon_selectors" in sections and driver:
            from Navigation_Bot.bots.navigationBot import NavigationBot
            self.processor.navibot = NavigationBot(driver, log_func=self.log)
            self.log("🔁 NavigationBot пересоздан")

        if "yandex_selectors" in sections:
            from Navigation_Bot.bots.mapsBot import MapsBot
            dm = getattr(self.processor, "driver_manager", None)
            if dm:
                self.processor.mapsbot = MapsBot(dm, log_func=self.log)
                self.log("🔁 MapsBot пересоздан")
            else:
                self.log("ℹ️ MapsBot обновится при запуске драйвера")

        if {"wialon_selectors", "yandex_selectors"} & sections and not driver:
            self.log("ℹ️ Селекторы применятся при старте веб-драйвера")

    def log(self, message: str):
        if self._log_enabled:
            self.log_box.append(message)

    def confirm_clear_json(self):
        reply = QMessageBox.question(self, "Подтверждение очистки",
                                     "Вы действительно хотите очистить все данные из JSON?\nЭто действие необратимо.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.data_context.set([])
            self.table_manager.display()

    def reload_and_show(self):
        with self.json_lock:
            self.data_context.reload()
            self.json_data = self.data_context.get()  # обновляем локальный alias
            init_processed_flags(self.json_data, self.json_data, loads_key="Выгрузка")
            self.data_context.save()

        if self.sort_controller.current == "buffer":
            self.sort_controller.sort_by_buffer()
        elif self.sort_controller.current == "arrival":
            self.sort_controller.sort_by_arrival()
        self.table_manager.display()

    def _on_header_clicked(self, logicalIndex: int):
        if logicalIndex == 0:  # 🔍 — открыть справочник ID
            self.open_id_manager()
            return
        if logicalIndex == 2:  # ТС
            self.sort_controller.sort_default()
            return
        if logicalIndex == 8:  # Запас
            self.sort_controller.sort_by_buffer()
            return
        if logicalIndex == 7:  # Время прибытия
            self.sort_controller.sort_by_arrival()
            return

    def open_id_editor(self, row):
        car = self.json_data[row]
        dialog = TrackingIdEditor(car, log_func=self.log, parent=self)
        if dialog.exec():
            self.data_context.set(self.json_data)
            self.table_manager.display()

    def open_id_manager(self):
        dlg = IDManagerDialog(self)
        if dlg.exec():
            self.table_manager.display()
            self.log("✅ Id_car.json перезаписан")
