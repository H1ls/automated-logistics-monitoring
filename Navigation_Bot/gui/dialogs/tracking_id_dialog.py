from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog
from Navigation_Bot.core.repositories.vehicle_registry_fields import vehicle_lookup_keys
from Navigation_Bot.core.repositories.postgres_vehicle_repository import (CENTER_FIELD,DB_ID_FIELD,
                                                                          DEFAULT_MONITORING_CENTER,
                                                                          ID_FIELD,NAME_FIELD,TS_FIELD)


class TrackingIdDialog(BaseDialog):
    def __init__(self, car_data, log_func=print, parent=None):
        super().__init__(title="Добавление ID", parent=parent, log_func=log_func)
        self.car_data = car_data

        self.vehicle_repository = getattr(parent, "vehicle_repository", None)
        if self.vehicle_repository is None:
            raise RuntimeError("TrackingIdDialog требуется parent.vehicle_repository")

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Введите ID")

        ts_value = (car_data.get("vehicle_plate") or car_data.get("ТС") or "").strip()
        self.ts_input = QLineEdit(ts_value)
        self.ts_input.setReadOnly(bool(ts_value))
        self.ts_input.setPlaceholderText("Введите ТС")

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_id)

        self.root.addWidget(QLabel("ID:"))
        self.root.addWidget(self.id_input)
        self.root.addWidget(QLabel("ТС:"))
        self.root.addWidget(self.ts_input)
        self.root.addWidget(save_button)

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

        new_monitoring_id = int(new_id)
        if self.vehicle_repository.exists_monitoring_id(new_monitoring_id, except_vehicle_id=existing_vehicle_id):
            existing_entry = self._find_existing_entry_by_monitoring_id(new_monitoring_id)
            if existing_entry is not None and self._entry_matches_ts(existing_entry, ts):
                self._apply_id_to_current_row(new_monitoring_id, existing_entry)
                self.log(f"✅ ID {new_id} уже есть в справочнике и привязан к ТС {ts}")
                self.accept()
                return
            self.log(f"⚠️ ID {new_id} уже существует.")
            return

        self.vehicle_repository.upsert_registry_entry({
            DB_ID_FIELD: existing_vehicle_id,
            ID_FIELD: new_monitoring_id,
            CENTER_FIELD: DEFAULT_MONITORING_CENTER,
            TS_FIELD: ts,
            NAME_FIELD: ts.replace(" ", ""),
        })
        self.log(f"✅ Добавлен ID {new_id} для ТС {ts}")

        self._apply_id_to_current_row(new_monitoring_id)
        self.accept()

    def _find_existing_entry_by_monitoring_id(self, monitoring_id: int) -> dict | None:
        for entry in self.vehicle_repository.list_registry_entries():
            try:
                entry_monitoring_id = int(entry.get(ID_FIELD) or entry.get("monitoring_id"))
            except (TypeError, ValueError):
                continue
            if entry_monitoring_id == monitoring_id:
                return entry
        return None

    @staticmethod
    def _entry_matches_ts(entry: dict, ts: str) -> bool:
        ts_keys = set(vehicle_lookup_keys(ts))
        entry_keys = set(vehicle_lookup_keys(entry.get(TS_FIELD),
                                             entry.get(NAME_FIELD),
                                             entry.get("plate_number"),
                                             entry.get("monitoring_name"),
                                             entry.get("vehicle_full_name")))
        return bool(ts_keys and entry_keys and ts_keys.intersection(entry_keys))

    def _apply_id_to_current_row(self, monitoring_id: int, entry: dict | None = None) -> None:
        self.car_data["id"] = monitoring_id
        self.car_data["vehicle_monitoring_id"] = monitoring_id
        if entry:
            plate = entry.get("plate_number")
            if plate:
                self.car_data["ТС"] = plate
                self.car_data["vehicle_plate"] = plate
