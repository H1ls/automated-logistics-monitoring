from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from Navigation_Bot.core.api_client import NavigationApiClient


def _to_row(item: Any) -> dict[str, Any]:
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    raise TypeError("history item must be dataclass or dict")


def _trip_number_from(item: dict[str, Any]) -> int | None:
    value = item.get("trip_number")
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


class _ApiHistoryBase:
    def __init__(self, client: NavigationApiClient, log: Callable[[str], None] | None = None):
        self.client = client
        self.log = log

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def _get_items(self, path: str) -> list[dict]:
        payload = self.client.get(path)
        return [row for row in payload.get("items", []) if isinstance(row, dict)]

    def _append_many_by_trip_number(self, items: list[Any], endpoint: str) -> None:
        for trip_number, rows in _group_rows_by_trip_number(items).items():
            self.client.post(f"/api/v1/tasks/{trip_number}/{endpoint}/batch", json={"items": rows})


class ApiStatusEventService(_ApiHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        trip_number = _trip_number_from(row)
        if trip_number is None:
            self._log("API status event skipped: missing trip_number")
            return
        self.client.post(f"/api/v1/tasks/{trip_number}/status-events", json={"item": row})

    def append_many(self, items: list[Any]) -> None:
        self._append_many_by_trip_number(items, "status-events")

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        return self._get_items(f"/api/v1/tasks/{trip_number}/status-events")


class ApiRouteEstimateHistoryService(_ApiHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        trip_number = _trip_number_from(row)
        if trip_number is None:
            self._log("API route estimate skipped: missing trip_number")
            return
        self.client.post(f"/api/v1/tasks/{trip_number}/route-estimates", json={"item": row})

    def append_estimate(self, estimate: Any) -> None:
        self.append(estimate)

    def append_many(self, items: list[Any]) -> None:
        self._append_many_by_trip_number(items, "route-estimates")

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        return self._get_items(f"/api/v1/tasks/{trip_number}/route-estimates")


class ApiNoteHistoryService(_ApiHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        trip_number = _trip_number_from(row)
        if trip_number is None:
            self._log("API note skipped: missing trip_number")
            return
        self.client.post(f"/api/v1/tasks/{trip_number}/notes", json=row)

    def append_many(self, items: list[Any]) -> None:
        self._append_many_by_trip_number(items, "notes")

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        return self._get_items(f"/api/v1/tasks/{trip_number}/notes")


class ApiNavigationHistoryService(_ApiHistoryBase):
    def append(self, item: Any) -> None:
        row = _to_row(item)
        trip_number = _trip_number_from(row)
        if trip_number is None:
            self._log("API navigation skipped: missing trip_number")
            return
        self.client.post(f"/api/v1/tasks/{trip_number}/navigation", json=row)

    def append_many(self, items: list[Any]) -> None:
        self._append_many_by_trip_number(items, "navigation")

    def append_snapshot(self, snapshot: Any) -> None:
        self.append(snapshot)

    def get_by_trip_number(self, trip_number: int) -> list[dict]:
        return self._get_items(f"/api/v1/tasks/{trip_number}/navigation")

    def get_by_vehicle_monitoring_id(self, vehicle_monitoring_id: int | str | None) -> list[dict]:
        try:
            monitoring_id = int(vehicle_monitoring_id)
        except (TypeError, ValueError):
            return []
        return self._get_items(f"/api/v1/vehicles/{monitoring_id}/navigation")


def _group_rows_by_trip_number(items: list[Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        row = _to_row(item)
        trip_number = _trip_number_from(row)
        if trip_number is None:
            continue
        grouped.setdefault(trip_number, []).append(row)
    return grouped
