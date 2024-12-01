import json
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Редактор JSON")
        self.resize(1200, 800)

        # Загружаем JSON
        with open("selected_data.json", "r", encoding="utf-8") as file:
            self.data = json.load(file)

        # Основной виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Основной лэйаут
        layout = QVBoxLayout(central_widget)

        # Панель кнопок
        buttons_layout = QHBoxLayout()
        buttons_info = [
            ("1. Excel", self.excel_function),
            ("2. Json", self.json_function),
            ("3. Sky", self.sky_function),
            ("4. Доп. окно", self.additional_window),
            ("5. Ввод машин", self.input_vehicle),
        ]

        for text, function in buttons_info:
            button = QPushButton(text)
            button.clicked.connect(function)
            button.setFixedHeight(100)  # Высота кнопок
            buttons_layout.addWidget(button)
        layout.addLayout(buttons_layout)

        # Таблица
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "№", "ID", "ТС", "Дата/Время Погрузка", "Погрузка",
            "Дата/Время Выгрузка", "Выгрузка", "Остаток КМ", "Остаток времени"
        ])

        # Устанавливаем параметры таблицы
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # №
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # ID
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)  # ТС
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)  # Дата/Время Погрузка
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)  # Погрузка
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)  # Дата/Время Выгрузка
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)  # Выгрузка
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Остаток КМ
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Остаток времени

        self.table.setEditTriggers(QTableWidget.AllEditTriggers)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.table)

        # Связывание данных с таблицей
        self.cell_mapping = {}
        self.populate_table()

        # Подключаем обработчик изменений
        self.table.cellChanged.connect(self.on_cell_changed)

    def populate_table(self):
        """Заполнение таблицы данными из JSON"""
        self.table.setRowCount(0)
        self.cell_mapping = {}

        for record_index, record in enumerate(self.data):
            record.setdefault("Погрузка", [])
            record.setdefault("Выгрузка", [])
            record.setdefault("Остаток КМ", "")
            record.setdefault("Остаток времени", "")

            max_points = max(len(record["Погрузка"]), len(record["Выгрузка"]), 1)
            for i in range(max_points):
                row = self.table.rowCount()
                self.table.insertRow(row)

                self.add_cell(row, 0, str(record.get("index", "")), record_index, "index")
                self.add_cell(row, 1, str(record.get("id", "")), record_index, "id")
                self.add_cell(row, 2, record.get("ТС", ""), record_index, "ТС")

                loading = record["Погрузка"][i] if i < len(record["Погрузка"]) else {}
                self.add_cell(row, 3, f"{loading.get('Дата 1', '')} {loading.get('Время 1', '')}", record_index, "Погрузка", i, "Дата/Время")
                self.add_cell(row, 4, loading.get("Точка 1", ""), record_index, "Погрузка", i, "Точка 1")

                unloading = record["Выгрузка"][i] if i < len(record["Выгрузка"]) else {}
                self.add_cell(row, 5, f"{unloading.get('Дата 1', '')} {unloading.get('Время 1', '')}", record_index, "Выгрузка", i, "Дата/Время")
                self.add_cell(row, 6, unloading.get("Точка 1", ""), record_index, "Выгрузка", i, "Точка 1")

                self.add_cell(row, 7, record.get("Остаток КМ", ""), record_index, "Остаток КМ")
                self.add_cell(row, 8, record.get("Остаток времени", ""), record_index, "Остаток времени")

    def add_cell(self, row, column, value, record_index, field_name, sub_index=None, sub_field=None):
        """Создание ячейки и привязка её к JSON"""
        item = QTableWidgetItem(value)
        if not value.strip():
            item.setBackground(QtGui.QColor("red"))  # Пустые ячейки красим в красный
        self.table.setItem(row, column, item)

        # Привязка ячейки к данным JSON
        self.cell_mapping[(row, column)] = {
            "record_index": record_index,
            "field_name": field_name,
            "sub_index": sub_index,
            "sub_field": sub_field
        }

    def on_cell_changed(self, row, column):
        """Обновление JSON при изменении ячейки"""
        if (row, column) not in self.cell_mapping:
            return

        mapping = self.cell_mapping[(row, column)]
        record_index = mapping["record_index"]
        field_name = mapping["field_name"]
        sub_index = mapping["sub_index"]
        sub_field = mapping["sub_field"]
        new_value = self.table.item(row, column).text()

        # Обновление данных в JSON
        if sub_index is not None and sub_field is not None:
            # Работаем с вложенными данными
            if field_name not in self.data[record_index]:
                self.data[record_index][field_name] = []
            while len(self.data[record_index][field_name]) <= sub_index:
                self.data[record_index][field_name].append({})
            self.data[record_index][field_name][sub_index][sub_field] = new_value
        else:
            # Работаем с простыми данными
            self.data[record_index][field_name] = new_value

        # Убираем красный фон, если ячейка заполнена
        if new_value.strip():
            self.table.item(row, column).setBackground(QtGui.QColor("white"))

        # Сохранение изменений в JSON
        self.save_data()

    def save_data(self):
        """Сохранение данных в JSON"""
        with open("selected_data.json", "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=4)
        print("Данные сохранены!")

    def excel_function(self):
        print("Функция Excel вызвана!")

    def json_function(self):
        print("Функция Json вызвана!")

    def sky_function(self):
        print("Функция Sky вызвана!")

    def additional_window(self):
        print("Функция Доп. окно вызвана!")

    def input_vehicle(self):
        print("Функция Ввод машин вызвана!")


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()
