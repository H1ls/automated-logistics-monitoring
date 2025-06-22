import os
import json
from PyQt6.QtCore import QTimer
from Navigation_Bot.jSONManager import JSONManager

INPUT_FILEPATH = "config/selected_data.json"


class JSONController:
    def __init__(self, parent, table_widget, log_func=None):
        self.parent = parent
        self.table = table_widget
        self.log = log_func or print
        self.file_path = INPUT_FILEPATH
        self.json_data = []
        self._log_enabled = True
        self.json_manager = JSONManager()

    def load_json(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                try:
                    self.json_data = json.load(f)
                except json.JSONDecodeError:
                    self.log("Ошибка чтения JSON")
                    self.json_data = []
        return self.json_data

    def save_on_edit(self, item):
        if not self._log_enabled:
            return
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

        if header == "id":
            try:
                value = int(value)
            except ValueError:
                self.log(f"Неверный формат id в строке {row + 1}")
                return

        old_value = self.json_data[row].get(header)
        if old_value == value:
            return

        self.json_data[row][header] = value
        JSONManager().save_in_json(self.json_data, self.file_path)
        self.log(f"Изменено: строка {row + 1}, колонка '{header}' → {value}")

    def save_all(self):
        JSONManager().save_in_json(self.json_data, self.file_path)

    def set_enabled(self, flag):
        self._log_enabled = flag

    def get_data(self):
        return self.json_data

    def set_data(self, data):
        self.json_data = data
        self.save_all()
