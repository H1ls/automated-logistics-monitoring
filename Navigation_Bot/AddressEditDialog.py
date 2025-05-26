from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QWidget, QTextEdit, QDateEdit
)
from PyQt6.QtCore import QDate


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
        layout = QHBoxLayout()

        label = QLabel(f"{self.prefix}")
        address_input = QTextEdit(address)
        address_input.setPlaceholderText("Адрес")
        address_input.setFixedHeight(60)
        address_input.setMinimumWidth(600)

        date_input = QDateEdit()
        date_input.setDisplayFormat("dd.MM.yyyy")
        date_input.setCalendarPopup(True)
        if date and date != "Не указано":
            try:
                day, month, year = map(int, date.split("."))
                date_input.setDate(QDate(year, month, day))
            except:
                date_input.setDate(QDate.currentDate())
        else:
            date_input.setDate(QDate.currentDate())

        time_input = QLineEdit(time)
        time_input.setPlaceholderText("чч:мм")
        time_input.setFixedWidth(100)

        btn_delete = QPushButton("🗑️")
        btn_delete.setFixedWidth(30)

        def handle_delete():
            self.remove_entry(container)

        btn_delete.clicked.connect(handle_delete)

        layout.addWidget(label)
        layout.addWidget(address_input)
        layout.addWidget(date_input)
        layout.addWidget(time_input)
        layout.addWidget(btn_delete)

        container.setLayout(layout)
        self.scroll_layout.addWidget(container)
        self.entries.append((container, address_input, date_input, time_input))

    def remove_entry(self, widget):
        for i, (container, *_ ) in enumerate(self.entries):
            if container == widget:
                self.scroll_layout.removeWidget(container)
                container.deleteLater()
                del self.entries[i]
                break

    def get_result(self):
        result = []
        for idx, (container, address_input, date_input, time_input) in enumerate(self.entries, 1):
            address = address_input.toPlainText().strip()
            date = date_input.date().toString("dd.MM.yyyy")
            time = time_input.text().strip()
            if address:
                result.append({
                    f"{self.prefix} {idx}": address,
                    f"Дата {idx}": date or "Не указано",
                    f"Время {idx}": time or "Не указано"
                })
        return result
