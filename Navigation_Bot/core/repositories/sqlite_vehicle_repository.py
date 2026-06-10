from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

ID_FIELD = "ИДОбъекта в центре мониторинга"
NAME_FIELD = "Наименование"
TS_FIELD = "ТС"
CENTER_FIELD = "Центр мониторинга"
DB_ID_FIELD = "_vehicle_db_id"


class SqliteVehicleRepository:
    """Справочник ТС в SQLite.

    Заменяет старый config/Id_car.json.

    Важно:
    - vehicles.plate_number хранит поисковое имя для Wialon из поля "Наименование";
    - vehicles.vehicle_full_name хранит информативное полное имя из поля "ТС";
    - vehicles.monitoring_name дублирует исходное "Наименование" для совместимости справочника.
    """

    def __init__(self, connection: sqlite3.Connection, log: Callable[[str], None] | None = None):
        self.connection = connection
        self.log = log

    def import_id_car_json(self, filepath: str | Path) -> int:
        """Идемпотентно импортирует старый Id_car.json в vehicles."""
        path = Path(filepath)
        if not path.exists():
            return 0

        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            self._log(f"Не удалось прочитать {path}: {exc}")
            return 0

        if not isinstance(payload, list):
            return 0

        imported = 0
        with self.connection:
            for entry in payload:
                if not isinstance(entry, dict):
                    continue
                if self.upsert_registry_entry(entry, commit=False) is not None:
                    imported += 1
        return imported

    def list_registry_entries(self) -> list[dict[str, Any]]:
        """Возвращает строки в формате старого Id_car.json для существующего GUI."""
        rows = self.connection.execute(
            """
            SELECT id, monitoring_id, monitoring_name, plate_number, monitoring_center, vehicle_full_name
            FROM vehicles
            WHERE monitoring_id IS NOT NULL
               OR monitoring_name <> ''
               OR monitoring_center <> ''
               OR vehicle_full_name <> ''
            ORDER BY plate_number COLLATE NOCASE, id
            """
        ).fetchall()
        return [self._row_to_legacy_entry(row) for row in rows]

    def save_registry_entries(self, entries: list[dict[str, Any]]) -> None:
        """Сохраняет отредактированные строки справочника в vehicles."""
        with self.connection:
            for entry in entries:
                if isinstance(entry, dict):
                    self.upsert_registry_entry(entry, commit=False)

    def upsert_registry_entry(self, entry: dict[str, Any], *, commit: bool = True) -> int | None:
        """Создает или обновляет ТС по db_id, monitoring_id или номеру."""
        monitoring_id = self._to_int_or_none(entry.get(ID_FIELD) or entry.get("id") or entry.get("monitoring_id"))
        monitoring_name = str(entry.get(NAME_FIELD) or entry.get("monitoring_name") or "").strip()
        vehicle_full_name = str(entry.get(TS_FIELD) or entry.get("vehicle_full_name") or "").strip()
        plate_number = str(entry.get("plate_number") or monitoring_name).strip()
        monitoring_center = str(entry.get(CENTER_FIELD) or entry.get("monitoring_center") or "").strip()
        db_id = self._to_int_or_none(entry.get(DB_ID_FIELD) or entry.get("vehicle_id"))

        if not plate_number:
            plate_number = self.compact_key(vehicle_full_name)
        if not monitoring_name and plate_number:
            monitoring_name = plate_number
        if not monitoring_center:
            monitoring_center = "Виалон"
        if not vehicle_full_name:
            vehicle_full_name = self.plate_from_monitoring_name(plate_number)
        if not plate_number:
            return None

        vehicle_id = self._find_vehicle_id(
            db_id=db_id,
            monitoring_id=monitoring_id,
            plate_number=plate_number,
            monitoring_name=monitoring_name,
        )

        if commit:
            with self.connection:
                return self._write_vehicle(
                    vehicle_id=vehicle_id,
                    monitoring_id=monitoring_id,
                    monitoring_name=monitoring_name,
                    plate_number=plate_number,
                    monitoring_center=monitoring_center,
                    vehicle_full_name=vehicle_full_name,
                )

        return self._write_vehicle(
            vehicle_id=vehicle_id,
            monitoring_id=monitoring_id,
            monitoring_name=monitoring_name,
            plate_number=plate_number,
            monitoring_center=monitoring_center,
            vehicle_full_name=vehicle_full_name,
        )

    def registry_lookup(self) -> dict[str, dict[str, Any]]:
        """Ключи без пробелов -> данные справочника для привязки рейсов к Wialon."""
        rows = self.connection.execute(
            """
            SELECT monitoring_id, monitoring_name, plate_number, vehicle_full_name
            FROM vehicles
            WHERE monitoring_id IS NOT NULL
            """
        ).fetchall()
        lookup: dict[str, dict[str, Any]] = {}
        for row in rows:
            monitoring_id = self._to_int_or_none(row["monitoring_id"])
            if monitoring_id is None:
                continue
            payload = {
                "monitoring_id": monitoring_id,
                "plate_number": row["plate_number"] or "",
                "monitoring_name": row["monitoring_name"] or "",
                "vehicle_full_name": row["vehicle_full_name"] or "",
            }
            for value in (row["monitoring_name"], row["plate_number"], row["vehicle_full_name"]):
                key = self.compact_key(value)
                if key:
                    lookup[key] = payload
        return lookup

    def monitoring_lookup(self) -> dict[str, int]:
        """Ключи без пробелов -> monitoring_id для старых мест вызова."""
        return {key: int(value["monitoring_id"]) for key, value in self.registry_lookup().items()}


    def monitoring_id_for_vehicle(self, vehicle_text: str) -> int | None:
        return self.monitoring_lookup().get(self.compact_key(vehicle_text))

    def exists_monitoring_id(self, monitoring_id: int, *, except_vehicle_id: int | None = None) -> bool:
        query = "SELECT id FROM vehicles WHERE monitoring_id = ?"
        params: tuple[Any, ...] = (monitoring_id,)
        if except_vehicle_id is not None:
            query += " AND id <> ?"
            params = (monitoring_id, except_vehicle_id)
        return self.connection.execute(query, params).fetchone() is not None

    def _write_vehicle(
            self,
            *,
            vehicle_id: int | None,
            monitoring_id: int | None,
            monitoring_name: str,
            plate_number: str,
            monitoring_center: str,
            vehicle_full_name: str,
    ) -> int:
        if vehicle_id is None:
            cursor = self.connection.execute(
                """
                INSERT INTO vehicles(plate_number, monitoring_id, monitoring_name, monitoring_center, vehicle_full_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plate_number, monitoring_id, monitoring_name, monitoring_center, vehicle_full_name),
            )
            return int(cursor.lastrowid)

        conflict = self.connection.execute(
            "SELECT id FROM vehicles WHERE plate_number = ? AND id <> ?",
            (plate_number, vehicle_id),
        ).fetchone()
        if conflict is not None:
            target_id = int(conflict["id"])
            self.connection.execute("UPDATE tasks SET vehicle_id = ? WHERE vehicle_id = ?", (target_id, vehicle_id))
            self.connection.execute(
                "UPDATE vehicle_navigation_history SET vehicle_id = ? WHERE vehicle_id = ?",
                (target_id, vehicle_id),
            )
            self.connection.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
            vehicle_id = target_id

        self.connection.execute(
            """
            UPDATE vehicles
            SET plate_number = ?,
                monitoring_id = ?,
                monitoring_name = ?,
                monitoring_center = ?,
                vehicle_full_name = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (plate_number, monitoring_id, monitoring_name, monitoring_center, vehicle_full_name, vehicle_id),
        )
        return vehicle_id

    def _find_vehicle_id(
            self,
            *,
            db_id: int | None,
            monitoring_id: int | None,
            plate_number: str,
            monitoring_name: str,
    ) -> int | None:
        if db_id is not None:
            found = self.connection.execute("SELECT id FROM vehicles WHERE id = ?", (db_id,)).fetchone()
            if found is not None:
                return int(found["id"])

        if monitoring_id is not None:
            found = self.connection.execute("SELECT id FROM vehicles WHERE monitoring_id = ?", (monitoring_id,)).fetchone()
            if found is not None:
                return int(found["id"])

        found = self.connection.execute("SELECT id FROM vehicles WHERE plate_number = ?", (plate_number,)).fetchone()
        if found is not None:
            return int(found["id"])

        if monitoring_name:
            found = self.connection.execute(
                "SELECT id FROM vehicles WHERE monitoring_name = ?",
                (monitoring_name,),
            ).fetchone()
            if found is not None:
                return int(found["id"])

        return None

    @staticmethod
    def compact_key(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "")).upper()

    @staticmethod
    def plate_from_monitoring_name(name: str) -> str:
        value = str(name or "").strip()
        if len(value) >= 7:
            return f"{value[0]} {value[1:4]} {value[4:6]} {value[6:]}"
        return value

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _row_to_legacy_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            DB_ID_FIELD: row["id"],
            ID_FIELD: row["monitoring_id"] if row["monitoring_id"] is not None else "",
            NAME_FIELD: row["monitoring_name"] or SqliteVehicleRepository.compact_key(row["plate_number"]),
            TS_FIELD: row["vehicle_full_name"] or row["plate_number"] or "",
            CENTER_FIELD: row["monitoring_center"] or "Виалон",
        }

    def _log(self, message: str) -> None:
        if self.log:
            self.log(message)
