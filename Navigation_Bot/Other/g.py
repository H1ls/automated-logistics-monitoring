import os
import sys
import json
from threading import Lock
from functools import partial
from PyQt6.QtCore import QTimer, Qt, QMetaObject, Q_ARG
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QPushButton, QTextEdit, QLabel, QHeaderView, QAbstractItemView)
from Navigation_Bot.bots.navigationBot import NavigationBot
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.genericSettingsDialog import GenericSettingsDialog
from Navigation_Bot.core.jSONManager import JSONManager
from Gui.settingsDialogManager import SettingsDialogManager


INPUT_FILEPATH = "config/selected_data.json"
ID_FILEPATH = "config/Id_car.json"


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Navigation Manager")
        self.resize(1400, 800)
        self.json_data = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.browser_opened = False
        self._log_enabled = True
        self.json_lock = Lock()
        self.gsheet = GoogleSheetsManager(log_func=self.log)
        self.updated_rows = []
        self._single_row_processing = True
        self.settings_ui = SettingsDialogManager(self)

        self.init_ui()
        self.load_json()
        self.display_data()

    def load_json(self):
        if os.path.exists(INPUT_FILEPATH):
            with open(INPUT_FILEPATH, "r", encoding="utf-8") as f:
                try:
                    self.json_data = json.load(f)
                except json.JSONDecodeError:
                    self.log("Ошибка чтения JSON")
                    self.json_data = []

    def init_ui(self):
        self.btn_wialon_combo = QPushButton("Wialon ⚙️")
        self.btn_yandex_combo = QPushButton("Я.Карты ⚙️")
        self.btn_load_google = QPushButton("Загрузить Задачи")
        self.btn_google_settings = QPushButton("Google ⚙️")
        self.btn_process_all = QPushButton("▶ Пробежать все ТС")
        self.btn_refresh_table = QPushButton("🔄 Обновить")
        self.btn_clear_json = QPushButton("🗑 Очистить JSON")

        for btn in [self.btn_wialon_combo,
                    self.btn_yandex_combo,
                    self.btn_load_google,
                    self.btn_google_settings,
                    self.btn_process_all,
                    self.btn_refresh_table,
                    self.btn_clear_json]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(130)

        # self.btn_wialon_combo.clicked.connect(self.open_wialon_settings)
        # self.btn_yandex_combo.clicked.connect(self.open_yandex_settings)
        # self.btn_google_settings.clicked.connect(self.open_google_settings)
        self.btn_wialon_combo.clicked.connect(self.settings_ui.open_wialon_settings)
        self.btn_yandex_combo.clicked.connect(self.settings_ui.open_yandex_settings)
        self.btn_google_settings.clicked.connect(self.settings_ui.open_google_settings)

        self.btn_load_google.clicked.connect(self.load_from_google)
        self.btn_process_all.clicked.connect(self.process_all)
        self.btn_refresh_table.clicked.connect(self.display_data)
        self.btn_clear_json.clicked.connect(self.confirm_clear_json)

        top = QHBoxLayout()
        top.addWidget(self.btn_wialon_combo)
        top.addWidget(self.btn_yandex_combo)
        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_google_settings)
        top.addWidget(self.btn_process_all)
        top.addWidget(self.btn_refresh_table)
        top.addWidget(self.btn_clear_json)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        # self.table.setHorizontalHeaderLabels(["", "id", "ТС", "Погрузка", "Выгрузка", "гео", "Время прибытия"])
        self.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "КА", "Погрузка", "Выгрузка", "гео", "Время прибытия", "Запас", ])

        self.table.setWordWrap(True)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 85)  # ТС
        self.table.setColumnWidth(3, 70)  # КА
        self.table.setColumnWidth(4, 500)
        self.table.setColumnWidth(5, 500)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setColumnHidden(1, True)
        self.table.cellDoubleClicked.connect(self.edit_cell_content)
        self.table.itemChanged.connect(self.save_to_json_on_edit)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(150)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Лог:"))
        layout.addWidget(self.log_box)
        self.setLayout(layout)
        self.table.setWordWrap(True)

    def display_data(self):

        self._log_enabled = False
        selected_row = self.table.currentRow()

        try:
            if not self.json_data:
                self.log("JSON пуст после загрузки — отображение отменено.")
                return

            self.table.setRowCount(0)

            for row_idx, row in enumerate(self.json_data):
                self.table.insertRow(row_idx)

                # ▶ кнопка запуска
                if row.get("id"):
                    btn = QPushButton("▶")
                    btn.clicked.connect(
                        lambda checked=False, idx=row_idx: self.executor.submit(self.process_row_wrapper, idx))
                else:
                    btn = QPushButton("🛠")
                    btn.setStyleSheet("color: red;")
                    btn.clicked.connect(partial(self.open_id_editor, row_idx))

                self.table.setCellWidget(row_idx, 0, btn)

                # 🛠 ID + кнопка
                id_value = str(row.get("id", ""))
                container = QWidget()
                layout = QHBoxLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                label = QLabel(id_value)
                btn_tool = QPushButton("🛠")
                btn_tool.setFixedWidth(30)
                btn_tool.clicked.connect(partial(self.open_id_editor, row_idx))
                layout.addWidget(label)
                layout.addWidget(btn_tool)
                layout.addStretch()
                container.setLayout(layout)
                self.table.setCellWidget(row_idx, 1, container)

                #  ТС + телефон
                ts = row.get("ТС", "")
                phone = row.get("Телефон", "")
                self.set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

                #  КА
                self.set_cell(row_idx, 3, row.get("КА", ""), editable=True)

                # Погрузка / Выгрузка
                self.set_cell(row_idx, 4, self.get_field_with_datetime(row, "Погрузка"))
                self.set_cell(row_idx, 5, self.get_field_with_datetime(row, "Выгрузка"))

                # Гео
                self.set_cell(row_idx, 6, row.get("гео", ""))
                # Время прибытия (col 7)
                arrival = row.get("Маршрут", {}).get("время прибытия", "—")
                arrival_item = QTableWidgetItem(arrival)
                arrival_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(row_idx, 7, arrival_item)

                # Запас времени (col 8)
                raw_buffer = row.get("Маршрут", {}).get("time_buffer", "—")

                if ":" in raw_buffer:
                    try:
                        h, m = map(int, raw_buffer.split(":"))
                        buffer = f"{h}ч {m}м"
                    except Exception:
                        buffer = raw_buffer
                else:
                    buffer = raw_buffer

                buffer_item = QTableWidgetItem(buffer)
                buffer_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(row_idx, 8, buffer_item)
                arrival_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                buffer_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setWordWrap(True)
            self.table.resizeRowsToContents()

            if selected_row >= 0 and selected_row < self.table.rowCount():
                self.table.selectRow(selected_row)

        except Exception as e:
            self.log(f"Ошибка в display_data(): {e}")

        self._log_enabled = True

    def confirm_clear_json(self):
        reply = QMessageBox.question(
            self,
            "Подтверждение очистки",
            "Вы действительно хотите очистить все данные из JSON?\nЭто действие необратимо.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            JSONManager().save_in_json([], INPUT_FILEPATH)
            self.log("🗑 JSON очищен.")
            self.load_json()
            self.display_data()

    def get_field_with_datetime(self, obj, key):
        if isinstance(obj.get(key), list):
            blocks = []
            for i, block in enumerate(obj[key], 1):
                date = block.get(f"Дата {i}", "")
                time = block.get(f"Время {i}", "")
                address = block.get(f"{key} {i}", "")
                entry = f"{date} {time}".strip()
                if entry and entry != "Не указано Не указано":
                    blocks.append(entry)
                if address:
                    blocks.append(address)
                if i < len(obj[key]):
                    blocks.append("____________________")
            return "\n".join(blocks)
        return ""

    def open_id_editor(self, row):
        from Navigation_Bot.TrackingIdEditor import TrackingIdEditor
        car = self.json_data[row]

        dialog = TrackingIdEditor(car, log_func=self.log, parent=self)
        if dialog.exec():
            JSONManager().save_in_json(self.json_data, INPUT_FILEPATH)
            self.display_data()

    def set_cell(self, row, col, value, editable=True):
        item = QTableWidgetItem(str(value) if value else "")
        if not value:
            item.setBackground(Qt.GlobalColor.red)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    def get_nested_field(self, obj, *fields):
        for field in fields:
            if isinstance(obj, list):
                obj = obj[0] if obj else {}
            obj = obj.get(field, {}) if isinstance(obj, dict) else {}
        return obj if isinstance(obj, str) else ""

    def log(self, text):
        print(text)
        QMetaObject.invokeMethod(
            self.log_box,
            "append",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, str(text))
        )

    def edit_cell_content(self, row, col):
        from Navigation_Bot.AddressEditDialog import AddressEditDialog

        col_name = self.table.horizontalHeaderItem(col).text()
        # self.log(f"Клик: строка {row + 1}, колонка '{col_name}'")
        print(f"Клик: строка {row + 1}, колонка '{col_name}'")

        if col_name in ["Погрузка", "Время погрузки"]:
            prefix = "Погрузка"
        elif col_name in ["Выгрузка", "Время выгрузки"]:
            prefix = "Выгрузка"
        else:
            return

        data_list = self.json_data[row].get(prefix, [])
        dialog = AddressEditDialog(self, data_list, prefix)
        if dialog.exec():
            merged = dialog.get_result()
            if not merged:
                self.log(f"{prefix}: Пустое редактирование в строке {row + 1} — изменения отменены.")
                return
            self.json_data[row][prefix] = merged
            self.display_data()
            JSONManager().save_in_json(self.json_data, INPUT_FILEPATH)
            self.log(f"{prefix} обновлены для строки {row + 1}")

    def save_to_json_on_edit(self, item):
        if not self._log_enabled:
            return

        QTimer.singleShot(0, lambda: self._save_item(item))

    def _save_item(self, item):
        row = item.row()
        col = item.column()
        header = self.table.horizontalHeaderItem(col).text()
        value = item.text()

        # 🔧 Нормализация: принудительно приводим "Гео" к "гео"
        if header.lower() == "гео":
            header = "гео"

        # Пропуск редактируемых вручную многострочных полей
        if header in ["Погрузка", "Выгрузка", "Время погрузки", "Время выгрузки"]:
            return

        if header == "id":
            try:
                value = int(value)
            except ValueError:
                self.log(f"Неверный формат id в строке {row + 1}")
                return

        old_value = self.json_data[row].get(header)
        if old_value == value:
            return

        with self.json_lock:
            self.json_data[row][header] = value
            JSONManager().save_in_json(self.json_data, INPUT_FILEPATH)

        self.log(f"Изменено: строка {row + 1}, колонка '{header}' → {value}")

    def load_from_google(self):
        self.log("📥 Загрузка данных из Google Sheets (в фоне)...")

        def background_task():
            try:
                # 🔁 Импорт внутри потока
                from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
                from Navigation_Bot.bots.dataCleaner import DataCleaner
                from Navigation_Bot.core.jSONManager import JSONManager

                data = self.gsheet.load_data()

                with self.json_lock:
                    self.gsheet.refresh_name(data, INPUT_FILEPATH)

                    cleaner = DataCleaner(JSONManager(), INPUT_FILEPATH, ID_FILEPATH, log_func=self.log)
                    cleaner.clean_vehicle_names()
                    cleaner.add_id_to_data()
                    cleaner.start_clean()

                QTimer.singleShot(0, self.reload_and_show)
                print("Завершена загрузка")
            except Exception as e:
                QTimer.singleShot(0, lambda: self.log(f"❌ Ошибка при загрузке: {e}"))

        self.executor.submit(background_task)

    def reload_and_show(self):
        with self.json_lock:
            self.load_json()
            self.json_data.sort(key=lambda x: x.get("index", 99999))

        self.display_data()
        self.log("✅ Обновление завершено.")

    def process_row_wrapper(self, row):
        try:
            car = self.json_data[row]
            if not car.get("ТС"):
                self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
                return

            self.init_driver_if_needed()
            updated = self.process_wialon_row(car)
            if not updated.get("_новые_координаты"):
                self.log(f"⚠️ Координаты не получены в этом запуске — пропуск Я.Карт для ТС {updated.get('ТС')}")
                return

            self.update_json_and_switch_to_yandex(row, updated)
            self.process_maps_and_write(updated, row)  # Включить

            QTimer.singleShot(0, self.display_data)
            self.log(f"✅ Завершено для ТС: {updated.get('ТС')}")

        except:
            self.log(f"❌ Ошибка в process_row_wrapper")

    def init_driver_if_needed(self):
        if not self.browser_opened or not hasattr(self, "driver_manager"):
            from Navigation_Bot.bots.webDriverManager import WebDriverManager
            self.driver_manager = WebDriverManager(log_func=self.log)
            self.driver_manager.start_browser()
            self.driver_manager.login_wialon()
            self.browser_opened = True
            self.log("✅ Драйвер и авторизация завершены.")

    def process_wialon_row(self, car):
        driver = self.driver_manager.driver
        driver.switch_to.window(driver.window_handles[0])
        self.log("🌐 Переключение на Wialon...")
        navibot = NavigationBot(driver, log_func=self.log)
        return navibot.process_row(car, switch_to_wialon=False)

    def update_json_and_switch_to_yandex(self, row, updated):
        updated.pop("_новые_координаты", None)  # удаляем временный маркер
        self.json_data[row] = updated
        JSONManager().save_in_json(self.json_data, INPUT_FILEPATH)
        self.driver_manager.open_yandex_maps()

    def process_maps_and_write(self, car, row_idx):
        maps_bot = MapsBot(self.driver_manager.driver, log_func=self.log)
        maps_bot.process_navigation_from_json(car)
        self.updated_rows.append(car)

        # 💾 Обновляем только одну строку и сохраняем JSON
        self.json_data[row_idx] = car
        JSONManager().save_in_json(self.json_data, INPUT_FILEPATH)

        # 📤 Если обрабатываем одну строку — пишем в таблицу
        if self._single_row_processing:
            self.gsheet.append_to_cell(car)
            self.log("📤 Данные записаны в Google Sheets")

    def process_all(self):
        self._single_row_processing = False
        self.updated_rows = []
        self.log("▶ Обработка всех ТС...")
        for row in range(self.table.rowCount()):
            car = self.json_data[row]
            if not car.get("ТС") or not car.get("id"):
                continue
            self.executor.submit(self.process_row_wrapper, row)
        QTimer.singleShot(5000, self.write_all_to_google)

    def write_all_to_google(self):
        if hasattr(self, "updated_rows") and self.updated_rows:
            try:
                self.gsheet.append_to_cell(self.updated_rows)
                self.log(f"📤 Обновлены все строки в Google Sheets ({len(self.updated_rows)} шт.)")
            except Exception as e:

                self.log(f"❌ Ошибка при групповой записи в Google Sheets: {e}")
            self.updated_rows = []


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = NavigationGUI()
    gui.show()
    sys.exit(app.exec())