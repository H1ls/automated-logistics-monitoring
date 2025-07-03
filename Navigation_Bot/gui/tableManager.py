from functools import partial
from PyQt6.QtWidgets import QTableWidgetItem, QPushButton, QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.gui.AddressEditDialog import AddressEditDialog

from Navigation_Bot.core.paths import INPUT_FILEPATH,ID_FILEPATH
# INPUT_FILEPATH = "config/selected_data.json"


"""TODO:1.json_data — передаётся и сохраняется напрямую self.json_data[row][...]
         Предложение: DataModel 
             Ввести отдельный DataModel, через который TableManager бы делал get(row, field) / set(row, field, value)
        2._save_item() растёт : Количество if-ов 
             Создать словарь стратегий:
                 self.field_savers = {
                   "ТС": self._save_ts_and_phone,
                   "id": self._save_id,
                 }
"""
class TableManager:
    def __init__(self, table_widget, json_data, log_func, on_row_click, on_edit_id_click):
        self.table = table_widget
        self.json_data = json_data
        self.log = log_func
        self.on_row_click = on_row_click
        self.on_edit_id_click = on_edit_id_click

    def display(self):
        scroll_value = self.table.verticalScrollBar().value()
        selected_row = self.table.currentRow()

        self.table.setRowCount(0)

        for row_idx, row in enumerate(self.json_data):
            self.table.insertRow(row_idx)

            # Кнопка ▶ или 🛠
            btn = QPushButton("▶" if row.get("id") else "🛠")
            if not row.get("id"):
                btn.setStyleSheet("color: red;")
                btn.clicked.connect(lambda _, idx=row_idx: self.on_edit_id_click(idx))
            else:
                btn.clicked.connect(lambda _, idx=row_idx: self.on_row_click(idx))
            self.table.setCellWidget(row_idx, 0, btn)

            # ID с кнопкой 🛠
            id_value = str(row.get("id", ""))
            container = QWidget()
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(id_value)
            btn_tool = QPushButton("🛠")
            btn_tool.setFixedWidth(30)
            # btn_tool.clicked.connect(lambda _, idx=row_idx: self.on_edit_id_click(idx))

            btn_tool.clicked.connect(partial(self.on_edit_id_click, row_idx))
            layout.addWidget(label)
            layout.addWidget(btn_tool)
            layout.addStretch()
            container.setLayout(layout)
            self.table.setCellWidget(row_idx, 1, container)

            # ТС + телефон
            ts = row.get("ТС", "")
            phone = row.get("Телефон", "")
            self._set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

            # КА
            self._set_cell(row_idx, 3, row.get("КА", ""), editable=True)

            # Погрузка / Выгрузка
            self._set_cell(row_idx, 4, self._get_field_with_datetime(row, "Погрузка"))
            self._set_cell(row_idx, 5, self._get_field_with_datetime(row, "Выгрузка"))

            # Гео
            self._set_cell(row_idx, 6, row.get("гео", ""))

            # Время прибытия
            arrival = row.get("Маршрут", {}).get("время прибытия", "—")
            self._set_readonly_cell(row_idx, 7, arrival)

            # Запас времени
            buffer = row.get("Маршрут", {}).get("time_buffer", "—")
            if ":" in buffer:
                try:
                    h, m = map(int, buffer.split(":"))
                    buffer = f"{h}ч {m}м"
                except Exception:
                    pass
            self._set_readonly_cell(row_idx, 8, buffer)

        self.table.resizeRowsToContents()
        self.table.verticalScrollBar().setValue(scroll_value)
        if 0 <= selected_row < self.table.rowCount():
            self.table.selectRow(selected_row)

    def _set_cell(self, row, col, value, editable=False):
        item = QTableWidgetItem(value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if not editable:
            item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)


    def _set_readonly_cell(self, row, col, value):
        item = QTableWidgetItem(str(value))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    @staticmethod
    def _get_field_with_datetime(row, key):
        if isinstance(row.get(key), list):
            blocks = []
            for i, block in enumerate(row[key], 1):
                date = block.get(f"Дата {i}", "")
                time = block.get(f"Время {i}", "")
                address = block.get(f"{key} {i}", "")
                entry = f"{date} {time}".strip()
                if entry and entry != "Не указано Не указано":
                    blocks.append(entry)
                if address:
                    blocks.append(address)
                if i < len(row[key]):
                    blocks.append("____________________")
            return "\n".join(blocks)
        return ""

    def edit_cell_content(self, row, col):

        col_name = self.table.horizontalHeaderItem(col).text()
        # self.log(f"Клик: строка {row + 1}, колонка '{col_name}'")
        if col_name in ["Погрузка", "Время погрузки"]:
            prefix = "Погрузка"
        elif col_name in ["Выгрузка", "Время выгрузки"]:
            prefix = "Выгрузка"
        else:
            return

        data_list = self.json_data[row].get(prefix, [])
        dialog = AddressEditDialog(self.table, data_list, prefix)
        if dialog.exec():
            merged = dialog.get_result()
            if not merged:
                self.log(f"{prefix}: Пустое редактирование в строке {row + 1} — изменения отменены.")
                return
            self.json_data[row][prefix] = merged
            JSONManager().save_in_json(self.json_data, str(INPUT_FILEPATH))
            self.log(f"{prefix} обновлены для строки {row + 1}")
            self.display()

    def save_to_json_on_edit(self, item):
        QTimer.singleShot(0, lambda: self._save_item(item))

    def _save_item(self, item):
        row = item.row()
        col = item.column()
        header = self.table.horizontalHeaderItem(col).text()
        value = item.text()

        if header.lower() == "гео":
            header = "гео"
        if header in ["Погрузка", "Выгрузка", "Время погрузки", "Время выгрузки"]:
            return

        # 🔧 Обработка колонки "ТС" (с телефоном)
        if header == "ТС":
            lines = value.splitlines()
            ts = lines[0] if lines else ""
            phone = lines[1] if len(lines) > 1 else ""

            old_ts = self.json_data[row].get("ТС", "")
            old_phone = self.json_data[row].get("Телефон", "")

            if ts == old_ts and phone == old_phone:
                return

            self.json_data[row]["ТС"] = ts
            self.json_data[row]["Телефон"] = phone
            JSONManager().save_in_json(self.json_data, str(INPUT_FILEPATH))
            # self.log(f"✏️ Изменено: строка {row + 1}, ТС → {ts}, Телефон → {phone}")
            return

        # Стандартное поведение
        if header == "id":
            try:
                value = int(value)
            except ValueError:
                self.log(f"⚠️ Неверный формат ID в строке {row + 1}")
                return

        old_value = self.json_data[row].get(header)
        if old_value == value:
            return

        self.json_data[row][header] = value
        JSONManager().save_in_json(self.json_data, str(INPUT_FILEPATH))
        # self.log(f"✏️ Изменено: строка {row + 1}, колонка '{header}' → {value}")
