import sys
import os
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QTextEdit, QLabel,
    QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import QTimer, Qt
from concurrent.futures import ThreadPoolExecutor

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
        self.init_ui()
        self.load_json()
        self.display_data()

    def init_ui(self):
        self.btn_wialon = QPushButton("Открыть Wialon")
        self.btn_yandex = QPushButton("Открыть Яндекс.Карты")
        self.btn_load_google = QPushButton("Загрузить из Google Sheets")
        self.btn_process_all = QPushButton("Обработать всё")
        self.btn_wialon.clicked.connect(self.open_wialon)
        self.btn_yandex.clicked.connect(self.open_yandex)

        self.btn_load_google.clicked.connect(lambda: self.executor.submit(self.load_from_google))
        self.btn_process_all.clicked.connect(self.process_all)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        # Столбец "Погрузка"
        self.table.setColumnWidth(4, 500)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

        # Столбец "Выгрузка"
        self.table.setColumnWidth(6, 500)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)

        self.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "Время погрузки", "Погрузка",
            "Время выгрузки", "Выгрузка", "Гео", "Время прибытия"
        ])
        self.table.setColumnWidth(0, 40)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(150)
        # Привязка двойного клика к редактированию адреса
        self.table.cellDoubleClicked.connect(self.edit_cell_content)
        self.table.itemChanged.connect(self.save_to_json_on_edit)

        layout = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(self.btn_wialon)
        top.addWidget(self.btn_yandex)
        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_process_all)

        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Лог:"))
        layout.addWidget(self.log_box)
        self.setLayout(layout)

    def load_json(self):
        if os.path.exists(INPUT_FILEPATH):
            with open(INPUT_FILEPATH, "r", encoding="utf-8") as f:
                try:
                    self.json_data = json.load(f)
                except json.JSONDecodeError:
                    self.log("Ошибка чтения JSON")
                    self.json_data = []

    def display_data(self):
        self._log_enabled = False

        try:
            if not self.json_data:
                self.log("JSON пуст после загрузки — отображение отменено.")
                return

            self.table.setRowCount(0)
            for row_idx, row in enumerate(self.json_data):
                self.table.insertRow(row_idx)

                # noinspection PyUnresolvedReferences
                btn = QPushButton("▶")
                btn.clicked.connect(lambda _, r=row_idx: self.executor.submit(self.process_row_wrapper, r))

                self.table.setCellWidget(row_idx, 0, btn)

                self.set_cell(row_idx, 1, row.get("id"), editable=True)
                self.set_cell(row_idx, 2, row.get("ТС"), editable=True)
                self.set_cell(row_idx, 3, self.get_datetime_combined(row.get("Погрузка", [])), editable=False)
                self.set_cell(row_idx, 4, self.get_field(row, "Погрузка"))
                self.set_cell(row_idx, 5, self.get_datetime_combined(row.get("Выгрузка", [])), editable=False)
                self.set_cell(row_idx, 6, self.get_field(row, "Выгрузка"))
                self.set_cell(row_idx, 7, row.get("гео", ""))
                self.set_cell(row_idx, 8, self.get_nested_field(row, "Маршрут", "Расчет прибытия", "время прибытия"))

                for col in [1, 2, 3, 5]:
                    self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                    text = self.table.item(row_idx, col).text()
                    width = max(20, min(300, len(text) * 7 + 5))
                    self.table.setColumnWidth(col, width)
                # self.table.setColumnWidth(1, len(text))  # id (7 символов + запас)
                # self.table.setColumnWidth(2, 120)  # ТС (9 символов + пробелы)
                # self.table.setColumnWidth(3, 190)  # Время погрузки ('Не указано — Не указано')
                # self.table.setColumnWidth(5, 190)  # Время выгрузки
                self.table.setRowHeight(row_idx, 60)

        except Exception as e:
            self.log(f"Ошибка в display_data(): {e}")
        self._log_enabled = True

    def set_cell(self, row, col, value, editable=True):
        item = QTableWidgetItem(str(value) if value else "")
        if not value:
            item.setBackground(Qt.GlobalColor.red)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    def get_field(self, obj, key):
        if isinstance(obj.get(key), list):
            items = obj[key]
            if len(items) == 1:
                # Без нумерации
                return items[0].get(f"{key} 1", "")
            else:
                # С нумерацией
                lines = []
                for i, block in enumerate(items, 1):
                    val = block.get(f"{key} {i}", "")
                    if val:
                        lines.append(f"{i}. {val}")
                return "\n".join(lines)
        return ""

    def get_datetime_combined(self, data):
        if isinstance(data, list):
            return "\n".join(
                f"{block.get(f'Дата {i + 1}', '')} — {block.get(f'Время {i + 1}', '')}".strip(" —")
                for i, block in enumerate(data)
                if block.get(f'Дата {i + 1}') or block.get(f'Время {i + 1}')
            )
        return ""

    def get_nested_field(self, obj, *fields):
        for field in fields:
            if isinstance(obj, list):
                obj = obj[0] if obj else {}
            obj = obj.get(field, {}) if isinstance(obj, dict) else {}
        return obj if isinstance(obj, str) else ""

    def log(self, text):
        self.log_box.append(text)

    def edit_cell_content(self, row, col):
        from Navigation_Bot.AddressEditDialog import AddressEditDialog

        col_name = self.table.horizontalHeaderItem(col).text()
        self.log(f"Клик: строка {row + 1}, колонка '{col_name}'")

        if col_name not in ["Погрузка", "Выгрузка", "Время погрузки", "Время выгрузки"]:
            return

        # Определяем, какой префикс редактируем
        prefix = "Погрузка" if "Погрузка" in col_name else "Выгрузка"

        data_list = self.json_data[row].get(prefix, [])
        dialog = AddressEditDialog(self, data_list, prefix)
        if dialog.exec():
            merged = dialog.get_result()
            if not merged:
                self.log(f"{prefix}: Пустое редактирование в строке {row + 1} — изменения отменены.")
                return
            self.json_data[row][prefix] = merged
            self.display_data()
            with open(INPUT_FILEPATH, "w", encoding="utf-8") as f:
                json.dump(self.json_data, f, ensure_ascii=False, indent=4)
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
            return  # ничего не изменилось

        self.json_data[row][header] = value
        with open(INPUT_FILEPATH, "w", encoding="utf-8") as f:
            json.dump(self.json_data, f, ensure_ascii=False, indent=4)
        self.log(f"Изменено: строка {row + 1}, колонка '{header}' → {value}")

    def load_from_google(self):
        from Navigation_Bot.googleSheetsManager import GoogleSheetsManager
        from Navigation_Bot.dataCleaner import DataCleaner
        from Navigation_Bot.jSONManager import JSONManager

        self.log("Загрузка данных из Google Sheets...")
        manager = GoogleSheetsManager()
        data = manager.load_data()
        manager.refresh_name(data, INPUT_FILEPATH)

        cleaner = DataCleaner(JSONManager(), INPUT_FILEPATH, ID_FILEPATH)
        cleaner.clean_vehicle_names()
        cleaner.add_id_to_data()
        cleaner.start_clean()

        self.load_json()
        QTimer.singleShot(0, self.display_data)
        self.log("Обновление завершено.")

    def open_wialon(self):
        from Navigation_Bot.webDriverManager import WebDriverManager
        self.log("Открытие Wialon...")
        WebDriverManager().open_wialon()

    def open_yandex(self):
        from Navigation_Bot.webDriverManager import WebDriverManager
        self.log("Открытие Яндекс.Карт...")
        WebDriverManager().open_yandex_maps()

    def process_row_wrapper(self, row):
        from Navigation_Bot.navigationBot import NavigationBot
        from Navigation_Bot.mapsBot import MapsBot
        from Navigation_Bot.jSONManager import JSONManager
        from Navigation_Bot.webDriverManager import WebDriverManager

        try:
            car = self.json_data[row]
            if not car.get("ТС") or not car.get("id"):
                self.log(f"⛔ Пропуск: нет ТС или ID в строке {row + 1}")
                return

            #1 Инициализация браузера
            if not self.browser_opened or not hasattr(self, "driver_manager"):
                self.driver_manager = WebDriverManager()
                self.driver_manager.start_browser()
                self.driver_manager.login_wialon()
                self.driver_manager.open_yandex_maps()
                self.browser_opened = True
                self.log("✅ Браузер и вкладки инициализированы.")

            #2 Запрос данных из Wialon
            navibot = NavigationBot(self.driver_manager.driver, log_func=self.log)
            updated = navibot.process_row(car)

            #3 Проверка наличия координат перед вызовом карты
            if not updated.get("коор"):
                self.log(f"⚠️ Пропуск Яндекс.Карт: координаты не получены для ТС {updated.get('ТС')}")
                return

            #4 Вызов Яндекс.Карт
            maps_bot = MapsBot(self.driver_manager.driver, log_func=self.log)
            maps_bot.process_navigation_from_json(updated)

            #5. Сохранение в JSON
            self.json_data[row] = updated
            JSONManager().save_json(self.json_data, INPUT_FILEPATH)

            #6 Обновление таблицы
            QTimer.singleShot(0, self.display_data)
            self.log(f"✅ Завершено для ТС: {updated.get('ТС')}")

        except Exception as e:
            self.log(f"❌ Ошибка в обработке строки {row + 1}: {e}")

    def process_all(self):
        self.log("Обработка всех ТС...")
        for i in range(len(self.json_data)):
            self.process_selected_row_logic(i)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = NavigationGUI()
    gui.show()
    sys.exit(app.exec())
