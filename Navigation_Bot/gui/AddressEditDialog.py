from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QLineEdit, QPushButton, QScrollArea, QWidget, QTextEdit, QDateEdit
)
from PyQt6.QtCore import QDate
import json
import os
from datetime import datetime, timedelta


class AddressEditDialog(QDialog):
    def __init__(self, parent, data_list, prefix):
        super().__init__(parent)
        self.setWindowTitle(f"Редактирование: {prefix}")
        self.prefix = prefix
        self.entries = []
        self.resize(1000, 500)

        self.layout = QVBoxLayout()
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_widget.setLayout(self.scroll_layout)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_widget)

        for i, item in enumerate(data_list, 1):
            address = item.get(f"{self.prefix} {i}", "")
            date = item.get(f"Дата {i}", "")
            time = item.get(f"Время {i}", "")
            self.add_entry(address, date, time)

        self.btn_add = QPushButton("➕ Добавить точку")
        self.btn_add.clicked.connect(lambda: self.add_entry())

        self.btn_save = QPushButton("✅ Сохранить")
        self.btn_save.clicked.connect(self.accept)

        self.layout.addWidget(self.scroll_area)
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_save)
        self.setLayout(self.layout)

    def add_entry(self, address="", date="", time=""):
        container = QWidget()
        wrapper = QVBoxLayout(container)

        # --- Верхняя строка: Дата выезда + Время + Транзит + Кнопка ---
        top_row = QHBoxLayout()

        dep_date = QLineEdit()
        dep_date.setInputMask("00.00.0000")
        dep_date.setPlaceholderText("дд.мм.гггг")
        dep_date.setFixedWidth(100)

        dep_time = QLineEdit()
        dep_time.setInputMask("00:00")
        dep_time.setPlaceholderText("чч:мм")
        dep_time.setFixedWidth(60)

        transit = QSpinBox()
        transit.setRange(0, 72)
        transit.setSuffix(" ч")

        btn_calc = QPushButton("🧮")
        btn_calc.setFixedWidth(30)

        top_row.addWidget(QLabel("Дата выезда:"))
        top_row.addWidget(dep_date)
        top_row.addWidget(dep_time)
        top_row.addWidget(QLabel("Транзит:"))
        top_row.addWidget(transit)
        top_row.addWidget(btn_calc)
        top_row.addStretch()

        # --- Нижняя строка: Адрес + Дата прибытия + Время + Удалить ---
        bottom_row = QHBoxLayout()
        label = QLabel(self.prefix)
        address_input = QTextEdit(address)
        address_input.setPlaceholderText("Адрес")
        address_input.setFixedHeight(60)
        address_input.setMinimumWidth(600)

        arr_date = QLineEdit()
        arr_date.setInputMask("00.00.0000")
        arr_date.setPlaceholderText("дд.мм.гггг")
        arr_date.setFixedWidth(100)
        if date:
            arr_date.setText(date)

        arr_time = QLineEdit()
        arr_time.setInputMask("00:00")
        arr_time.setPlaceholderText("чч:мм")
        arr_time.setFixedWidth(60)
        arr_time.setText(time[:5] if time else "")

        btn_delete = QPushButton("🗑️")
        btn_delete.setFixedWidth(30)
        btn_delete.clicked.connect(lambda: self.remove_entry(container))

        bottom_row.addWidget(label)
        bottom_row.addWidget(address_input)
        bottom_row.addWidget(arr_date)
        bottom_row.addWidget(arr_time)
        bottom_row.addWidget(btn_delete)

        # --- Кнопка расчёта даты прибытия ---
        def calculate_arrival():
            try:
                dep_dt = datetime.strptime(dep_date.text().strip(), "%d.%m.%Y")
                dep_tm = datetime.strptime(dep_time.text().strip(), "%H:%M").time()
                full_dt = datetime.combine(dep_dt.date(), dep_tm)
                if transit.value() <= 0:
                    return
                arrival_dt = full_dt + timedelta(hours=transit.value())
                arr_date.setText(arrival_dt.strftime("%d.%m.%Y"))
                arr_time.setText(arrival_dt.strftime("%H:%M"))
                container._meta = {
                    "Время отправки": full_dt.strftime("%d.%m.%Y %H:%M"),
                    "Транзит": f"{transit.value()} ч"
                }
            except Exception as e:
                print(f"[DEBUG] ❌ Ошибка расчёта: {e}")

        btn_calc.clicked.connect(calculate_arrival)

        wrapper.addLayout(top_row)
        wrapper.addLayout(bottom_row)
        self.scroll_layout.addWidget(container)
        self.entries.append((container, address_input, arr_date, arr_time))

    def remove_entry(self, widget):
        for i, (container, *_) in enumerate(self.entries):
            if container == widget:
                self.scroll_layout.removeWidget(container)
                container.deleteLater()
                del self.entries[i]
                break

    def get_result(self):
        result = []
        meta_result = {}

        for idx, (container, address_input, date_input, time_input) in enumerate(self.entries, 1):
            address = address_input.toPlainText().strip()
            date = date_input.text().strip()  # 💥 было: .date().toString(...)
            time = time_input.text().strip()
            if not address:
                continue
            row = {
                f"{self.prefix} {idx}": address,
                f"Дата {idx}": date or "Не указано",
                f"Время {idx}": time or "Не указано"
            }
            result.append(row)

            if hasattr(container, "_meta"):
                meta = container._meta
                if meta.get("Время отправки"):
                    meta_result["Время отправки"] = meta["Время отправки"]
                if meta.get("Транзит"):
                    meta_result["Транзит"] = meta["Транзит"]

        return result, meta_result
