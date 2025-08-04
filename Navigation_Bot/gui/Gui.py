import os
import sys
import json
from threading import Lock
from PyQt6.QtCore import QTimer
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QTextEdit,
                             QLabel, QHeaderView, QAbstractItemView, QMessageBox)
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.gui.combinedSettingsDialog import CombinedSettingsDialog
from Navigation_Bot.gui.settingsDialogManager import SettingsDialogManager
from Navigation_Bot.gui.iDManagerDialog import IDManagerDialog
from Navigation_Bot.gui.tableManager import TableManager
from Navigation_Bot.navigationProcessor import NavigationProcessor
from Navigation_Bot.core.paths import INPUT_FILEPATH, ID_FILEPATH
from Navigation_Bot.core.processedFlags import init_processed_flags

"""TODO:1.Дублируется self.json_data -> передаётся в:TableManager NavigationProcessor
         Но в load_from_google() -> self.json_data = self.processor.gsheet.load_from_google()
         Предложение:
             Сделать self.json_data централизованным классом-хранилищем (DataContext или JsonDataStore) 
             и передавать его как объект.
        2.Перекинуть _submit_processor_row в NavigationProcessor"""


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Navigation Manager")
        self.resize(1030, 1033)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._log_enabled = True
        self.json_lock = Lock()
        self.updated_rows = []
        self._single_row_processing = True

        self.json_data = JSONManager(INPUT_FILEPATH, log_func=self.log).load_json() or []

        self.init_ui()

        self.settings_ui = CombinedSettingsDialog(self)
        # print(f"[DEBUG] Gui self.json_data id: {id(self.json_data)}")

        self.table_manager = TableManager(
            table_widget=self.table,

            json_data=self.json_data,
            log_func=self.log,
            on_row_click=self._submit_processor_row,
            on_edit_id_click=self.open_id_editor
        )
        self.gsheet = GoogleSheetsManager(log_func=self.log)

        self.processor = NavigationProcessor(
            json_data=self.json_data,
            logger=self.log,
            # gsheet=GoogleSheetsManager(log_func=self.log),
            gsheet=self.gsheet,
            filepath=str(INPUT_FILEPATH),
            display_callback=self.reload_and_show,
            single_row=self._single_row_processing,
            updated_rows=self.updated_rows
        )

        self.connect_signals()
        self.table_manager.display()

    def init_ui(self):
        layout = QVBoxLayout()
        top = QHBoxLayout()

        # Верхние кнопки
        # self.btn_wialon_combo = QPushButton("Wialon ⚙️")
        # self.btn_yandex_combo = QPushButton("Я.Карты ⚙️")
        # self.btn_google_settings = QPushButton("Google ⚙️")
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
        # top.addWidget(btn)

        # top = QHBoxLayout()
        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_process_all)
        top.addWidget(self.btn_refresh_table)
        top.addWidget(self.btn_clear_json)
        top.addWidget(self.btn_settings)
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "КА", "Погрузка", "Выгрузка","гео", "Время прибытия", "Запас"
        ])

        self.table.setWordWrap(True)
        # self.table.setWordWrap(True)
        self.table.setColumnWidth(0, 40)  #
        self.table.setColumnWidth(1, 40)  # id
        self.table.setColumnWidth(2, 80)  # ТС
        self.table.setColumnWidth(3, 30)  # КА
        self.table.setColumnWidth(4, 270) # Погрузка
        self.table.setColumnWidth(5, 275) # Выгрузка
        self.table.setColumnWidth(6, 65)  # гео
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
        self.btn_settings.clicked.connect(lambda: CombinedSettingsDialog.open_all_settings(self))
        self.btn_process_all.clicked.connect(self.processor.process_all)
        self.btn_refresh_table.clicked.connect(self.table_manager.display)
        self.table.itemChanged.connect(self.table_manager.save_to_json_on_edit)
        self.btn_clear_json.clicked.connect(self.confirm_clear_json)
        self.btn_load_google.clicked.connect(self.load_from_google)

    def _submit_processor_row(self, row_idx):
        if 0 <= row_idx < len(self.json_data):
            self.executor.submit(self.processor.process_row_wrapper, row_idx)
        else:
            self.log(f"⚠️ Строка {row_idx} больше не существует. Пропуск.")

    def log(self, message: str):
        if self._log_enabled:
            self.log_box.append(message)

    def confirm_clear_json(self):
        reply = QMessageBox.question(
            self,
            "Подтверждение очистки",
            "Вы действительно хотите очистить все данные из JSON?\nЭто действие необратимо.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.json_data = []
            JSONManager().save_in_json(self.json_data, str(INPUT_FILEPATH))
            self.table_manager.json_data = self.json_data
            self.table_manager.display()

    def open_id_editor(self, row):
        from Navigation_Bot.gui.trackingIdEditor import TrackingIdEditor
        car = self.json_data[row]

        dialog = TrackingIdEditor(car, log_func=self.log, parent=self)
        if dialog.exec():
            JSONManager().save_in_json(self.json_data, str(INPUT_FILEPATH))
            self.table_manager.display()

    def load_from_google(self):
        self.log("📥 Загрузка данных из Google Sheets...")

        def background_task():
            try:
                # 🔁 Импорт внутри потока
                from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
                from Navigation_Bot.bots.dataCleaner import DataCleaner
                from Navigation_Bot.core.jSONManager import JSONManager

                data = self.gsheet.load_data()

                with self.json_lock:
                    self.gsheet.refresh_name(data, str(INPUT_FILEPATH))

                    try:
                        cleaner = DataCleaner(log_func=self.log)
                        cleaner.start_clean()

                        clean_data  = JSONManager().load_json(str(INPUT_FILEPATH)) or []

                        init_processed_flags(clean_data, clean_data, loads_key="Выгрузка")
                        JSONManager().save_in_json(clean_data, str(INPUT_FILEPATH))
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        print(f"[ERROR] Ошибка в cleaner: {e}")

                QTimer.singleShot(0, self.reload_and_show)
            except Exception as e:
                QTimer.singleShot(0, lambda: self.log(f"❌ Ошибка при загрузке: {e}"))

        self.executor.submit(background_task)

    def reload_and_show(self):
        with self.json_lock:
            self.json_data = JSONManager().load_json(str(INPUT_FILEPATH)) or []
            self.json_data.sort(key=lambda x: x.get("index", 99999))
            init_processed_flags(self.json_data, self.json_data, loads_key="Выгрузка")
            JSONManager().save_in_json(self.json_data, str(INPUT_FILEPATH))
            self.table_manager.json_data = self.json_data
            self.processor.json_data = self.json_data

        self.table_manager.display()
        self.log("✅ Обновление завершено.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = NavigationGUI()
    gui.show()
    sys.exit(app.exec())
