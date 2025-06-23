from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout
import json
import os

ID_CAR_PATH = "config/Id_car.json"


class TrackingIdEditor(QDialog):
    def __init__(self, car_data, log_func=print, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление ID")
        self.car_data = car_data
        self.log = log_func

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

        entry = {
            "ИДОбъекта в центре мониторинга": int(new_id),
            "Центр мониторинга": "Виалон",
            "ТС": ts,
            "Наименование": ts.replace(" ", "")
        }

        try:
            with open(ID_CAR_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = []

        if not any(x["ИДОбъекта в центре мониторинга"] == int(new_id) for x in data):
            data.append(entry)
            with open(ID_CAR_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.log(f"✅ Добавлен ID {new_id} для ТС {ts}")
        else:
            self.log(f"⚠️ ID {new_id} уже существует.")

        self.car_data["id"] = int(new_id)
        self.accept()
