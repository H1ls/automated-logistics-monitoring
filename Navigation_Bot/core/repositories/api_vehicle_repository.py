from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.api_client import NavigationApiClient
from Navigation_Bot.core.repositories.vehicle_registry_fields import (
    DB_ID_FIELD,
    ID_FIELD,
    NAME_FIELD,
    TS_FIELD,
    compact_vehicle_key,
)


@dataclass(slots=True)
class ApiVehicleRepository:
    client: NavigationApiClient
    log: Callable[[str], None] | None = None
    _entries: list[dict[str, Any]] | None = None
    _snapshot: dict[str, dict[str, Any]] | None = None

    def list_registry_entries(self) -> list[dict[str, Any]]:
        if self._entries is not None:
            return deepcopy(self._entries)

        payload = self.client.get("/api/v1/vehicles")
        rows = [row for row in payload.get("items", []) if isinstance(row, dict)]
        self._entries = deepcopy(rows)
        self._snapshot = {self._entry_key(row): self._normalized_entry(row) for row in rows}
        return deepcopy(rows)

    def save_registry_entries(self, entries: list[dict[str, Any]]) -> None:
        snapshot = self._snapshot or {}
        changed_count = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = self._entry_key(entry)
            normalized = self._normalized_entry(entry)
            if snapshot.get(key) == normalized:
                continue
            self.upsert_registry_entry(entry)
            changed_count += 1
        if self.log:
            pass
            # self.log(f"API vehicles saved: {changed_count} changed")
        self._entries = None
        self._snapshot = None

    def upsert_registry_entry(self, entry: dict[str, Any], *, commit: bool = True) -> int | None:
        payload = self.client.post("/api/v1/vehicles", json={"entry": entry})
        vehicle_id = payload.get("vehicle_id")
        self._entries = None
        self._snapshot = None
        return int(vehicle_id) if vehicle_id is not None else None

    def registry_lookup(self) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for entry in self.list_registry_entries():
            monitoring_id = self._to_int_or_none(entry.get("monitoring_id") or entry.get(ID_FIELD))
            if monitoring_id is None:
                continue
            payload = {"monitoring_id": monitoring_id,
                       "plate_number": entry.get("plate_number") or entry.get(NAME_FIELD) or "",
                       "monitoring_name": entry.get("monitoring_name") or entry.get(NAME_FIELD) or "",
                       "vehicle_full_name": entry.get("vehicle_full_name") or entry.get(TS_FIELD) or "",
                       }
            for value in (payload["monitoring_name"],
                          payload["plate_number"],
                          payload["vehicle_full_name"],
                          entry.get(NAME_FIELD),
                          entry.get(TS_FIELD)
                          ):
                key = compact_vehicle_key(value)
                if key:
                    lookup[key] = payload
        return lookup

    def monitoring_lookup(self) -> dict[str, int]:
        return {key: int(value["monitoring_id"]) for key, value in self.registry_lookup().items()}

    def monitoring_id_for_vehicle(self, vehicle_text: str) -> int | None:
        return self.monitoring_lookup().get(compact_vehicle_key(vehicle_text))

    def exists_monitoring_id(self, monitoring_id: int, *, except_vehicle_id: int | None = None) -> bool:
        for entry in self.list_registry_entries():
            entry_monitoring_id = self._to_int_or_none(entry.get("monitoring_id") or entry.get(ID_FIELD))
            entry_db_id = self._to_int_or_none(entry.get(DB_ID_FIELD) or entry.get("vehicle_id"))
            if entry_monitoring_id == monitoring_id and entry_db_id != except_vehicle_id:
                return True
        return False

    @classmethod
    def _entry_key(cls, entry: dict[str, Any]) -> str:
        db_id = cls._to_int_or_none(entry.get(DB_ID_FIELD) or entry.get("vehicle_id"))
        if db_id is not None:
            return f"db:{db_id}"
        monitoring_id = cls._to_int_or_none(entry.get("monitoring_id") or entry.get(ID_FIELD))
        if monitoring_id is not None:
            return f"monitoring:{monitoring_id}"
        plate = compact_vehicle_key(entry.get("plate_number") or entry.get(NAME_FIELD) or entry.get(TS_FIELD))
        return f"plate:{plate}"

    @classmethod
    def _normalized_entry(cls, entry: dict[str, Any]) -> dict[str, Any]:
        return {DB_ID_FIELD: cls._to_int_or_none(entry.get(DB_ID_FIELD) or entry.get("vehicle_id")),
                ID_FIELD: cls._to_int_or_none(entry.get("monitoring_id") or entry.get(ID_FIELD)),
                NAME_FIELD: str(entry.get("monitoring_name") or entry.get(NAME_FIELD) or "").strip(),
                TS_FIELD: str(entry.get("vehicle_full_name") or entry.get(TS_FIELD) or "").strip(),
                "plate_number": str(entry.get("plate_number") or "").strip(),
                }

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
