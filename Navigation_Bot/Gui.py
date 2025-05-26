import os
import sys
import json
from threading import Lock
from functools import partial
from PyQt6.QtCore import QTimer, Qt,QMetaObject, Q_ARG
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QTextEdit, QLabel,
    QHeaderView, QAbstractItemView
)

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

        self.json_lock = Lock()

    def init_ui(self):
        self.btn_wialon = QPushButton("Wialon")
        self.btn_yandex = QPushButton("Я.Карты")
        self.btn_load_google = QPushButton("Загрузить Задачи")
        self.btn_process_all = QPushButton("▶ Пробежать все ТС")

        for btn in [self.btn_wialon, self.btn_yandex, self.btn_load_google, self.btn_process_all]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(110)

        # Добавляем кнопки-настройки
        self.btn_settings_wialon = QPushButton("⚙️")
        self.btn_settings_yamap = QPushButton("⚙️")
        for b in [self.btn_settings_wialon, self.btn_settings_yamap]:
            b.setFixedSize(28, 28)
            b.setToolTip("Настройки")

        self.btn_settings_wialon.setEnabled(False)  # пока заглушка
        self.btn_settings_yamap.setEnabled(False)
        self.btn_load_google.clicked.connect(self.load_from_google)
        self.btn_process_all.clicked.connect(self.process_all)
        self.btn_wialon.clicked.connect(self.open_wialon)
        self.btn_yandex.clicked.connect(self.open_yandex)

        top = QHBoxLayout()
        top.addWidget(self.btn_wialon)
        top.addWidget(self.btn_settings_wialon)
        top.addWidget(self.btn_yandex)
        top.addWidget(self.btn_settings_yamap)
        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_process_all)

        self.table = QTableWidget()
        self.table.setColumnCount(7)

        self.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "Погрузка",
            "Выгрузка", "гео", "Время прибытия"
        ])

        self.table.setColumnWidth(0, 40)  # ▶ кнопка
        self.table.setColumnWidth(2, 85)  # ТС
        self.table.setColumnWidth(3, 500)  # Погрузка
        self.table.setColumnWidth(4, 500)  # Выгрузка

        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)

        self.table.setColumnHidden(1, True)  # скрыть id

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(150)

        self.table.cellDoubleClicked.connect(self.edit_cell_content)
        self.table.itemChanged.connect(self.save_to_json_on_edit)

        layout = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(self.btn_wialon)
        top.addWidget(self.btn_settings_wialon)
        top.addWidget(self.btn_yandex)
        top.addWidget(self.btn_settings_yamap)
        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_process_all)

        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Лог:"))
        layout.addWidget(self.log_box)
        self.setLayout(layout)

        self.table.setWordWrap(True)

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

                # ▶ или 🛠 если нет ID
                has_id = bool(str(row.get("id", "")).strip())

                if has_id:
                    btn = QPushButton("▶")
                    btn.clicked.connect(lambda _, idx=row_idx: self.executor.submit(self.process_row_wrapper, idx))
                else:
                    btn = QPushButton("🛠")
                    btn.setStyleSheet("color: red;")
                    btn.clicked.connect(partial(self.open_id_editor, row_idx))

                self.table.setCellWidget(row_idx, 0, btn)

                # id (скрытая колонка, но сохраняется)
                id_value = str(row.get("id", ""))
                container = QWidget()
                layout = QHBoxLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                label = QLabel(id_value)
                layout.addWidget(label)
                layout.addStretch()
                container.setLayout(layout)
                self.table.setCellWidget(row_idx, 1, container)

                # ТС
                ts = row.get("ТС", "")
                phone = row.get("Телефон", "")
                self.set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

                # Погрузка и Выгрузка: дата + время + адрес
                self.set_cell(row_idx, 3, self.get_field_with_datetime(row, "Погрузка"))
                self.set_cell(row_idx, 4, self.get_field_with_datetime(row, "Выгрузка"))

                # Гео
                self.set_cell(row_idx, 5, row.get("гео", ""))

                # Время прибытия (если есть)
                self.set_cell(
                    row_idx, 6,
                    self.get_nested_field(row, "Маршрут", "Расчет прибытия", "время прибытия")
                )

            # Автовысота строк
            self.table.setWordWrap(True)
            self.table.resizeRowsToContents()

        except Exception as e:
            self.log(f"Ошибка в display_data(): {e}")

        self._log_enabled = True

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
            from Navigation_Bot.jSONManager import JSONManager
            JSONManager().save_json(self.json_data, INPUT_FILEPATH)
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
        self.log(f"Клик: строка {row + 1}, колонка '{col_name}'")

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
            with open(INPUT_FILEPATH, "w", encoding="utf-8") as f:
                json.dump(self.json_data, f, ensure_ascii=False, indent=4)

        self.log(f"Изменено: строка {row + 1}, колонка '{header}' → {value}")

    def load_from_google(self):
        self.log("📥 Загрузка данных из Google Sheets (в фоне)...")

        def background_task():
            try:
                # 🔁 Импорт внутри потока
                from Navigation_Bot.googleSheetsManager import GoogleSheetsManager
                from Navigation_Bot.dataCleaner import DataCleaner
                from Navigation_Bot.jSONManager import JSONManager

                manager = GoogleSheetsManager()
                data = manager.load_data()

                with self.json_lock:
                    manager.refresh_name(data, INPUT_FILEPATH)

                    cleaner = DataCleaner(JSONManager(), INPUT_FILEPATH, ID_FILEPATH,log_func=self.log)
                    cleaner.clean_vehicle_names()
                    cleaner.add_id_to_data()
                    cleaner.start_clean()

                QTimer.singleShot(0, self.reload_and_show)

            except Exception as e:
                QTimer.singleShot(0, lambda: self.log(f"❌ Ошибка при загрузке: {e}"))

        self.executor.submit(background_task)

    def reload_and_show(self):
        with self.json_lock:
            self.load_json()
        self.display_data()
        self.log("✅ Обновление завершено.")

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
            if not car.get("ТС"):
                self.log(f"⛔ Пропуск: нет ТС в строке {row + 1}")
                return

            # 1. Инициализация WebDriver
            if not self.browser_opened or not hasattr(self, "driver_manager"):
                self.driver_manager = WebDriverManager(log_func=self.log)

                self.log("🌐 Запуск браузера...")
                self.driver_manager.start_browser()
                self.log("🔐 Авторизация в Wialon...")
                self.driver_manager.login_wialon()
                self.browser_opened = True
                self.log("✅ Браузер и авторизация завершены.")

            driver = self.driver_manager.driver

            # 2. Переключение на вкладку Wialon
            driver.switch_to.window(driver.window_handles[0])
            self.log("🌐 Переключение на вкладку Wialon...")

            # 3. Обработка через Wialon, уже переключились вручную
            navibot = NavigationBot(driver, log_func=self.log)
            updated = navibot.process_row(car, switch_to_wialon=False)

            if not updated.get("коор"):
                self.log(f"⚠️ Пропуск Яндекс.Карт: координаты не получены для ТС {updated.get('ТС')}")
                return

            # 4. ⚠️ Обновляем JSON ДО вызова карт
            self.json_data[row] = updated
            JSONManager().save_json(self.json_data, INPUT_FILEPATH)

            # 5. Переключение/открытие Яндекс.Карт
            if not self.driver_manager.switch_to_yandex_tab(log_func=self.log):
                self.driver_manager.open_yandex_maps()
                driver.switch_to.window(driver.window_handles[-1])
                self.log("🗺️ Открыта новая вкладка Яндекс.Карт.")

            # 6. Расчёт маршрута
            maps_bot = MapsBot(driver, log_func=self.log)
            maps_bot.process_navigation_from_json(updated)

            # 7. Обновление таблицы
            QTimer.singleShot(0, self.display_data)
            self.log(f"✅ Завершено для ТС: {updated.get('ТС')}")

        except Exception as e:
            self.log(f"❌ Ошибка в process_row_wrapper: {e}")

    def process_all(self):
        self.log("Обработка всех ТС...")
        for i in range(len(self.json_data)):
            self.process_selected_row_logic(i)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = NavigationGUI()
    gui.show()
    sys.exit(app.exec())
