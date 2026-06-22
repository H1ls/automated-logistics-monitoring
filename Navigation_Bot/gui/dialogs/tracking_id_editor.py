from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from Navigation_Bot.core.repositories.postgres_vehicle_repository import (CENTER_FIELD,
                                                                          DB_ID_FIELD,
                                                                          DEFAULT_MONITORING_CENTER,
                                                                          ID_FIELD,
                                                                          NAME_FIELD,
                                                                          TS_FIELD)


class TrackingIdEditor(QDialog):
    def __init__(self, car_data, log_func=print, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление ID")
        self.car_data = car_data
        self.log = log_func

        self.vehicle_repository = getattr(parent, "vehicle_repository", None)
        if self.vehicle_repository is None:
            raise RuntimeError("TrackingIdEditor requires parent.vehicle_repository")

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

        existing_vehicle_id = None
        for entry in self.vehicle_repository.list_registry_entries():
            if entry.get(TS_FIELD) == ts:
                existing_vehicle_id = entry.get(DB_ID_FIELD)
                break

        if self.vehicle_repository.exists_monitoring_id(int(new_id), except_vehicle_id=existing_vehicle_id):
            self.log(f"⚠️ ID {new_id} уже существует.")
            return

        self.vehicle_repository.upsert_registry_entry({
            DB_ID_FIELD: existing_vehicle_id,
            ID_FIELD: int(new_id),
            CENTER_FIELD: DEFAULT_MONITORING_CENTER,
            TS_FIELD: ts,
            NAME_FIELD: ts.replace(" ", ""),
        })
        self.log(f"✅ Добавлен ID {new_id} для ТС {ts}")

        self.car_data["id"] = int(new_id)
        self.accept()
