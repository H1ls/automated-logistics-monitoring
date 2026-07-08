from __future__ import annotations

import re
from typing import Any, Callable

from Navigation_Bot.core.repositories.vehicle_registry_fields import (
    CENTER_FIELD,
    DB_ID_FIELD,
    DEFAULT_MONITORING_CENTER,
    ID_FIELD,
    NAME_FIELD,
    TS_FIELD,
    compact_vehicle_key,
    plate_from_monitoring_name,
    vehicle_lookup_keys,
)
from Navigation_Bot.core.logging import noop_log, normalize_log_func


class PostgresVehicleRepository:
    def __init__(self, connection: Any, log: Callable[[str], None] | None = None):
        self.connection = connection
        self.log = normalize_log_func(log or noop_log)

    def list_registry_entries(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, monitoring_id, monitoring_name, plate_number, monitoring_center, vehicle_full_name
            FROM vehicles
            WHERE monitoring_id IS NOT NULL
               OR monitoring_name <> ''
               OR monitoring_center <> ''
               OR vehicle_full_name <> ''
            ORDER BY plate_number, id
            """
        ).fetchall()
        return [self._row_to_legacy_entry(row) for row in rows]

    def save_registry_entries(self, entries: list[dict[str, Any]]) -> None:
        normalized = [self._normalize_registry_entry(entry) for entry in entries if isinstance(entry, dict)]
        normalized = [entry for entry in normalized if entry is not None]
        normalized = self._dedupe_registry_entries(normalized)
        with self.connection.transaction():
            for entry in normalized:
                vehicle_id = self._find_vehicle_id(db_id=None,
                                                   monitoring_id=entry["monitoring_id"],
                                                   plate_number=entry["plate_number"],
                                                   monitoring_name=entry["monitoring_name"])
                self._write_vehicle(vehicle_id=vehicle_id, **entry)

    def delete_registry_entry(self, entry: dict[str, Any]) -> bool:
        vehicle_id = self._find_vehicle_id_for_entry(entry)
        if vehicle_id is None:
            return False
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE vehicles
                SET monitoring_id = NULL,
                    monitoring_name = '',
                    monitoring_center = '',
                    vehicle_full_name = '',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (vehicle_id,),
            )
        return True

    def upsert_registry_entry(self, entry: dict[str, Any], *, commit: bool = True) -> int | None:
        normalized = self._normalize_registry_entry(entry)
        if normalized is None:
            return None
        monitoring_id = normalized["monitoring_id"]
        monitoring_name = normalized["monitoring_name"]
        vehicle_full_name = normalized["vehicle_full_name"]
        plate_number = normalized["plate_number"]
        monitoring_center = normalized["monitoring_center"]
        db_id = self._to_int_or_none(entry.get(DB_ID_FIELD) or entry.get("vehicle_id"))

        vehicle_id = self._find_vehicle_id(db_id=db_id,
                                           monitoring_id=monitoring_id,
                                           plate_number=plate_number,
                                           monitoring_name=monitoring_name)

        if commit:
            with self.connection.transaction():
                return self._write_vehicle(vehicle_id=vehicle_id,
                                           monitoring_id=monitoring_id,
                                           monitoring_name=monitoring_name,
                                           plate_number=plate_number,
                                           monitoring_center=monitoring_center,
                                           vehicle_full_name=vehicle_full_name)

        return self._write_vehicle(vehicle_id=vehicle_id,
                                   monitoring_id=monitoring_id,
                                   monitoring_name=monitoring_name,
                                   plate_number=plate_number,
                                   monitoring_center=monitoring_center,
                                   vehicle_full_name=vehicle_full_name)

    def _normalize_registry_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        monitoring_id = self._to_int_or_none(entry.get(ID_FIELD) or entry.get("id") or entry.get("monitoring_id"))
        monitoring_name = str(entry.get(NAME_FIELD) or entry.get("monitoring_name") or "").strip()
        vehicle_full_name = str(entry.get(TS_FIELD) or entry.get("vehicle_full_name") or "").strip()
        plate_number = str(entry.get("plate_number") or monitoring_name).strip()
        monitoring_center = str(entry.get(CENTER_FIELD) or entry.get("monitoring_center") or "").strip()

        if not plate_number:
            plate_number = self.compact_key(vehicle_full_name)
        plate_number = self.format_plate_number(plate_number)
        if not monitoring_name and plate_number:
            monitoring_name = plate_number
        monitoring_name = self.format_plate_number(monitoring_name)
        if not monitoring_center:
            monitoring_center = DEFAULT_MONITORING_CENTER
        if not vehicle_full_name:
            vehicle_full_name = self.plate_from_monitoring_name(plate_number)
        if not plate_number:
            return None

        return {"monitoring_id": monitoring_id,
                "monitoring_name": monitoring_name,
                "plate_number": plate_number,
                "monitoring_center": monitoring_center,
                "vehicle_full_name": vehicle_full_name}

    @staticmethod
    def _dedupe_registry_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_monitoring_id: dict[int, dict[str, Any]] = {}
        without_monitoring_id: list[dict[str, Any]] = []
        for entry in entries:
            monitoring_id = entry.get("monitoring_id")
            if monitoring_id is None:
                without_monitoring_id.append(entry)
            else:
                by_monitoring_id[int(monitoring_id)] = entry

        by_plate: dict[str, dict[str, Any]] = {}
        for entry in [*without_monitoring_id, *by_monitoring_id.values()]:
            by_plate[str(entry["plate_number"])] = entry
        return list(by_plate.values())

    def registry_lookup(self) -> dict[str, dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT monitoring_id, monitoring_name, plate_number, vehicle_full_name
            FROM vehicles
            WHERE monitoring_id IS NOT NULL
            """
        ).fetchall()
        lookup: dict[str, dict[str, Any]] = {}
        base_candidates: dict[str, dict[str, Any] | None] = {}
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
                exact_key = compact_vehicle_key(value)
                if exact_key:
                    lookup[exact_key] = payload
                for key in vehicle_lookup_keys(value):
                    if key and key != exact_key:
                        existing = base_candidates.get(key)
                        if key not in base_candidates:
                            base_candidates[key] = payload
                        elif existing is not None and existing.get("monitoring_id") != payload.get("monitoring_id"):
                            base_candidates[key] = None

        for key, payload in base_candidates.items():
            if payload is not None and key not in lookup:
                lookup[key] = payload
        return lookup

    def monitoring_lookup(self) -> dict[str, int]:
        return {key: int(value["monitoring_id"]) for key, value in self.registry_lookup().items()}

    def monitoring_id_for_vehicle(self, vehicle_text: str) -> int | None:
        return self.monitoring_lookup().get(self.compact_key(vehicle_text))

    def exists_monitoring_id(self, monitoring_id: int, *, except_vehicle_id: int | None = None) -> bool:
        query = "SELECT id FROM vehicles WHERE monitoring_id = %s"
        params: tuple[Any, ...] = (monitoring_id,)
        if except_vehicle_id is not None:
            query += " AND id <> %s"
            params = (monitoring_id, except_vehicle_id)
        return self.connection.execute(query, params).fetchone() is not None

    def _write_vehicle(self,
                       *,
                       vehicle_id: int | None,
                       monitoring_id: int | None,
                       monitoring_name: str,
                       plate_number: str,
                       monitoring_center: str,
                       vehicle_full_name: str, ) -> int:
        if vehicle_id is None:
            row = self.connection.execute(
                """
                INSERT INTO vehicles(plate_number, monitoring_id, monitoring_name, monitoring_center, vehicle_full_name)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(plate_number) DO UPDATE SET
                    monitoring_id = COALESCE(excluded.monitoring_id, vehicles.monitoring_id),
                    monitoring_name = excluded.monitoring_name,
                    monitoring_center = excluded.monitoring_center,
                    vehicle_full_name = excluded.vehicle_full_name,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (plate_number, monitoring_id, monitoring_name, monitoring_center, vehicle_full_name),
            ).fetchone()
            return int(row["id"])

        conflict = self.connection.execute(
            "SELECT id FROM vehicles WHERE plate_number = %s AND id <> %s", (plate_number, vehicle_id), ).fetchone()
        if conflict is not None:
            target_id = int(conflict["id"])
            self.connection.execute("UPDATE tasks SET vehicle_id = %s WHERE vehicle_id = %s", (target_id, vehicle_id))
            self.connection.execute(
                "UPDATE vehicle_navigation_history SET vehicle_id = %s WHERE vehicle_id = %s",
                (target_id, vehicle_id))
            self.connection.execute("DELETE FROM vehicles WHERE id = %s", (vehicle_id,))
            vehicle_id = target_id

        self.connection.execute(
            """
            UPDATE vehicles
            SET plate_number = %s,
                monitoring_id = %s,
                monitoring_name = %s,
                monitoring_center = %s,
                vehicle_full_name = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (plate_number, monitoring_id, monitoring_name, monitoring_center, vehicle_full_name, vehicle_id))
        return vehicle_id

    def _find_vehicle_id(self, *,
                         db_id: int | None,
                         monitoring_id: int | None,
                         plate_number: str,
                         monitoring_name: str, ) -> int | None:
        checks = []
        if db_id is not None:
            checks.append(("SELECT id FROM vehicles WHERE id = %s", (db_id,)))
        if monitoring_id is not None:
            checks.append(("SELECT id FROM vehicles WHERE monitoring_id = %s", (monitoring_id,)))
        checks.append(("SELECT id FROM vehicles WHERE plate_number = %s", (plate_number,)))
        if monitoring_name:
            checks.append(("SELECT id FROM vehicles WHERE monitoring_name = %s", (monitoring_name,)))

        for query, params in checks:
            found = self.connection.execute(query, params).fetchone()
            if found is not None:
                return int(found["id"])
        return None

    def _find_vehicle_id_for_entry(self, entry: dict[str, Any]) -> int | None:
        db_id = self._to_int_or_none(entry.get(DB_ID_FIELD) or entry.get("vehicle_id"))
        monitoring_id = self._to_int_or_none(entry.get(ID_FIELD) or entry.get("id") or entry.get("monitoring_id"))
        plate_number = str(entry.get("plate_number") or entry.get(NAME_FIELD) or "").strip()
        monitoring_name = str(entry.get(NAME_FIELD) or entry.get("monitoring_name") or "").strip()

        normalized = self._normalize_registry_entry(entry)
        if normalized is not None:
            plate_number = normalized["plate_number"]
            monitoring_name = normalized["monitoring_name"]
            monitoring_id = normalized["monitoring_id"]

        return self._find_vehicle_id(db_id=db_id,
                                     monitoring_id=monitoring_id,
                                     plate_number=plate_number,
                                     monitoring_name=monitoring_name)

    @staticmethod
    def compact_key(value: Any) -> str:
        return compact_vehicle_key(value)

    @staticmethod
    def format_plate_number(value: Any) -> str:
        text = str(value or "").strip().upper()
        compact = re.sub(r"\s+", "", text)
        match = re.fullmatch(r"([^\W\d_])(\d{3})([^\W\d_]{2})(\d{2,3})", compact, re.UNICODE)
        if not match:
            return text
        return f"{match.group(1)}{match.group(2)}{match.group(3)} {match.group(4)}"

    @staticmethod
    def plate_from_monitoring_name(name: str) -> str:
        return plate_from_monitoring_name(name)

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _row_to_legacy_entry(row: dict[str, Any]) -> dict[str, Any]:
        return {DB_ID_FIELD: row["id"],
                ID_FIELD: row["monitoring_id"] if row["monitoring_id"] is not None else "",
                NAME_FIELD: row["monitoring_name"] or PostgresVehicleRepository.compact_key(row["plate_number"]),
                TS_FIELD: row["vehicle_full_name"] or row["plate_number"] or "",
                CENTER_FIELD: row["monitoring_center"] or DEFAULT_MONITORING_CENTER}
