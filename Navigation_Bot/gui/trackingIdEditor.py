from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout
from Navigation_Bot.core.paths import ID_FILEPATH
from Navigation_Bot.core.jSONManager import JSONManager

"""TODO 1.Логика self.car_data["id"] = int(new_id) 
        2.Проверка дубликатов
"""

class TrackingIdEditor(QDialog):
    def __init__(self, car_data, log_func=print, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление ID")
        self.car_data = car_data
        self.log = log_func

        self.json_manager = JSONManager(file_path=ID_FILEPATH, log_func=self.log)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Введите ID")

        ts_value = car_data.get("ТС", "").strip()
        self.ts_input = QLineEdit(ts_value)
        self.ts_input.setReadOnly(bool(ts_value))
        self.ts_input.setPlaceholderText("Введите ТС")

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_id)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("ID:"))
        layout.addWidget(self.id_input)
        layout.addWidget(QLabel("ТС:"))
        layout.addWidget(self.ts_input)
        layout.addWidget(save_button)
        self.setLayout(layout)

    def save_id(self):
        new_id = self.id_input.text().strip()
        ts = self.ts_input.text().strip()

        if not new_id.isdigit() or not ts:
            self.log("⚠️ Введите корректные данные.")
            return

        new_entry = {
            "ИДОбъекта в центре мониторинга": int(new_id),
            "Центр мониторинга": "Виалон",
            "ТС": ts,
            "Наименование": ts.replace(" ", "")
        }

        try:
            data = self.json_manager.load_json()
        except Exception:
            data = []

        if not isinstance(data, list):
            data = []

        if any(x.get("ИДОбъекта в центре мониторинга") == int(new_id) for x in data):
            self.log(f"⚠️ ID {new_id} уже существует.")
        else:
            data.append(new_entry)
            self.json_manager.save_in_json(data)
            self.log(f"✅ Добавлен ID {new_id} для ТС {ts}")

        self.car_data["id"] = int(new_id)
        self.accept()
