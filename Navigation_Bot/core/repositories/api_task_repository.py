from __future__ import annotations

import json
from os import getenv
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.api_client import NavigationApiClient
from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper


@dataclass(slots=True)
class ApiTaskRepository:
    client: NavigationApiClient
    log: Callable[[str], None] | None = None
    data: list[dict] | None = None
    _snapshot: dict[str, str] | None = None
    _snapshot_rows: dict[str, dict[str, Any]] | None = None
    current_source_key: str = ""
    _defer_sync: bool = False
    _pending_sync_rows: dict[str, dict[str, Any]] | None = None
    _last_loaded_updated_at: str = ""

    _FINGERPRINT_IGNORED_FIELDS = {
        "db_task_id",
        "task_id",
        "trip_number",
        "updated_at",
        "vehicle_plate",
        "vehicle_monitoring_id",
        "driver_name",
        "driver_phone",
        "carrier_name",
        "loads",
        "unloads",
        "processed_unloads",
        "navigation",
        "route_estimate",
        "geo_zona",
        "gps_fix_age",
        "_новые_координаты",
        "Маршрут",
        "гео",
        "коор",
        "скорость",
    }

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def set_source_key(self, source_key: str, *, reload: bool = True) -> None:
        new_source_key = str(source_key or "")
        if new_source_key != self.current_source_key:
            self.data = None
            self._snapshot = None
            self._snapshot_rows = None
            self._last_loaded_updated_at = ""
        self.current_source_key = new_source_key
        if reload:
            self.reload()

    def reload(self) -> None:
        page_size = self._configured_page_size()
        self.reload_all_paged(limit=page_size)

    def reload_page(self,
                    *,
                    limit: int = 100,
                    offset: int = 0,
                    strict_source_key: bool = True) -> dict[str, Any]:
        payload = self.client.get("/api/v1/tasks",
                                  params={"source_key": self.current_source_key,
                                          "strict_source_key": str(bool(strict_source_key)).lower(),
                                          "limit": int(limit),
                                          "offset": int(offset)})
        return payload if isinstance(payload, dict) else {}

    def reload_all_paged(self, *, limit: int = 500, strict_source_key: bool = True) -> None:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.reload_page(limit=limit, offset=offset, strict_source_key=strict_source_key)
            page_rows = [row for row in payload.get("items", []) if isinstance(row, dict)]
            rows.extend(page_rows)
            next_offset = payload.get("next_offset")
            if next_offset is None:
                break
            offset = int(next_offset)
        self._replace_data(rows)

    def reload_incremental(self,
                           *,
                           updated_since: str | None = None,
                           limit: int = 500,
                           offset: int = 0,
                           strict_source_key: bool = True) -> dict[str, Any]:
        since = updated_since or self._last_loaded_updated_at
        params = {"source_key": self.current_source_key,
                  "strict_source_key": str(bool(strict_source_key)).lower(),
                  "limit": int(limit),
                  "offset": int(offset)}
        if since:
            params["updated_since"] = since

        payload = self.client.get("/api/v1/tasks", params=params)
        rows = [row for row in payload.get("items", []) if isinstance(row, dict)] if isinstance(payload, dict) else []
        if rows:
            self._merge_rows(rows)
        return payload if isinstance(payload, dict) else {"count": 0, "items": []}

    def reload_incremental_all(self, *, limit: int = 500, strict_source_key: bool = True) -> dict[str, Any]:
        since = self._last_loaded_updated_at
        offset = 0
        total_changed = 0
        last_payload: dict[str, Any] = {"count": 0, "items": [], "next_offset": None}
        while True:
            payload = self.reload_incremental(updated_since=since,
                                              limit=limit,
                                              offset=offset,
                                              strict_source_key=strict_source_key)
            total_changed += int(payload.get("count") or 0)
            last_payload = payload
            next_offset = payload.get("next_offset")
            if next_offset is None:
                break
            offset = int(next_offset)
        last_payload["count"] = total_changed
        return last_payload

    def refresh_incremental_or_reload(self, *, limit: int | None = None) -> dict[str, Any]:
        page_size = limit or self._configured_page_size() or 500
        if self.data is None or not self._last_loaded_updated_at:
            self.reload_all_paged(limit=page_size)
            return {"mode": "reload", "count": len(self.data or [])}
        try:
            payload = self.reload_incremental_all(limit=page_size)
            payload["mode"] = "incremental"
            return payload
        except Exception:
            self.reload_all_paged(limit=page_size)
            return {"mode": "reload", "count": len(self.data or [])}

    def get(self) -> list[dict]:
        if self.data is None:
            self.reload()
        return self.data if self.data is not None else []

    def list_tasks(self) -> list[Task]:
        return [TaskMapper.from_dict(row) for row in self.get() if isinstance(row, dict)]

    def get_by_index(self, index_key: int) -> Task | None:
        for row in self.get():
            if isinstance(row, dict) and row.get("index") == index_key:
                return TaskMapper.from_dict(row)
        return None

    def save(self, *, source: str = "user") -> None:
        self.sync_rows(self.get(), source=source)

    def set(self, new_data: list, *, source: str = "user") -> None:
        rows = [row for row in new_data if isinstance(row, dict)]
        self.sync_rows(rows, source=source)
        self.data = rows

    def append(self, entry: dict, *, source: str = "user") -> None:
        data = self.get()
        data.append(entry)
        self.upsert_from_row(entry, source=source)

    def save_task(self, task: Task, *, source: str = "user") -> None:
        task.ensure_processing_consistency()
        task_dict = TaskMapper.to_dict(task)
        index_key = task.index
        data = self.get()
        for i, row in enumerate(data):
            if isinstance(row, dict) and row.get("index") == index_key:
                merged = {**task_dict, **{k: v for k, v in row.items() if k not in task_dict}}
                data[i] = merged
                self.upsert_from_row(merged, source=source)
                return
        data.append(task_dict)
        self.upsert_from_row(task_dict, source=source)

    def replace_all(self, tasks: list[Task], *, source: str = "user") -> None:
        rows = []
        for task in tasks:
            task.ensure_processing_consistency()
            rows.append(TaskMapper.to_dict(task))
        self.set(rows, source=source)

    def delete_by_index(self, index_key: int) -> bool:
        data = self.get()
        for i, row in enumerate(data):
            if isinstance(row, dict) and row.get("index") == index_key:
                row_identity = row.get("trip_number") or row.get("google_sheet_row") or row.get("index")
                if row_identity is None:
                    return False
                self.client.post(f"/api/v1/tasks/{int(row_identity)}/complete",
                                 json={"source": "user",
                                       "source_key": self.current_source_key} )
                data.pop(i)
                return True
        return False

    def complete_row(self, real_idx: int, *, source: str = "user") -> tuple[bool, dict | None, str | None]:
        data = self.get()
        if not (0 <= real_idx < len(data)):
            return False, None, "row_out_of_range"
        row = data[real_idx]

        if not isinstance(row, dict):
            return False, None, "row_not_dict"
        row_identity = row.get("trip_number") or row.get("google_sheet_row") or row.get("index")

        if row_identity is None:
            return False, None, "missing_row_identity"

        self.client.post(f"/api/v1/tasks/{int(row_identity)}/complete",
                         json={"source": source,
                               "source_key": self.current_source_key})

        removed = data.pop(real_idx)
        return True, removed, None

    def complete_rows(self, row_identities: list[int], *, source: str = "user") -> dict[str, Any]:
        payload = self.client.post("/api/v1/tasks/complete/batch",
                                   json={"row_identities": row_identities,
                                         "source": source,
                                         "source_key": self.current_source_key})
        completed = {int(item) for item in payload.get("items", [])}
        if self.data is not None and completed:
            self.data = [
                row for row in self.data
                if self._row_identity_int(row) not in completed
            ]
            self._snapshot = self._build_snapshot(self.data)
            self._snapshot_rows = self._build_snapshot_rows(self.data)
        return payload

    def sync_rows(self, rows: list[dict], *, source: str = "user") -> None:
        snapshot = self._snapshot or {}
        snapshot_rows = self._snapshot_rows or {}
        changed_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            fingerprint = self._row_fingerprint(row)
            if self._snapshot_fingerprint_for_row(snapshot, row) == fingerprint:
                continue

            changed_fields = self._changed_fields(snapshot_rows, row)
            if source == "user" and changed_fields == {"processed"}:
                continue

            changed_rows.append(row)
        if changed_rows and self._defer_sync:
            pending = self._pending_sync_rows if self._pending_sync_rows is not None else {}
            for row in changed_rows:
                pending[self._row_key(row)] = row
            self._pending_sync_rows = pending
            return

        if changed_rows:
            self._upsert_rows_batch(changed_rows, source=source)
        self._snapshot = self._build_snapshot(rows)
        self._snapshot_rows = self._build_snapshot_rows(rows)
        # if self.log:
        #     self.log(f"API tasks saved: {len(changed_rows)} changed")

    def begin_deferred_sync(self) -> None:
        self._defer_sync = True
        self._pending_sync_rows = {}

    def flush_deferred_sync(self, *, source: str = "user") -> None:
        pending = list((self._pending_sync_rows or {}).values())
        self._pending_sync_rows = {}
        if pending:
            self._upsert_rows_batch(pending, source=source)
        if self.data is not None:
            self._snapshot = self._build_snapshot(self.data)
            self._snapshot_rows = self._build_snapshot_rows(self.data)

    def end_deferred_sync(self, *, source: str = "user") -> None:
        try:
            self.flush_deferred_sync(source=source)
        finally:
            self._defer_sync = False

    def upsert_from_row(self, row: dict[str, Any], *, source: str = "user") -> dict[str, int] | None:
        payload = self.client.post("/api/v1/tasks",
                                   json={"row": row,
                                         "source": source,
                                         "source_key": self.current_source_key}
                                   )
        result = {key: int(payload[key])
                  for key in ("task_id", "trip_number")
                  if key in payload and payload[key] is not None
                  }
        row.update(result)
        if payload.get("updated_at") is not None:
            row["updated_at"] = payload["updated_at"]

        if self.data is not None:
            self._snapshot = self._build_snapshot(self.data)
            self._snapshot_rows = self._build_snapshot_rows(self.data)
        return result

    def _upsert_rows_batch(self, rows: list[dict[str, Any]], *, source: str = "user") -> list[dict[str, int]]:
        payload = self.client.post("/api/v1/tasks/batch",
                                   json={"rows": rows,
                                         "source": source,
                                         "source_key": self.current_source_key
                                         }
                                   )

        items = [item for item in payload.get("items", []) if isinstance(item, dict)]
        for row, item in zip(rows, items):
            result = {key: int(item[key])
                      for key in ("task_id", "trip_number")
                      if key in item and item[key] is not None}
            row.update(result)
            if item.get("updated_at") is not None:
                row["updated_at"] = item["updated_at"]
        return items

    def _replace_data(self, rows: list[dict[str, Any]]) -> None:
        copied = deepcopy(rows)
        self.data = copied
        self._snapshot = self._build_snapshot(copied)
        self._snapshot_rows = self._build_snapshot_rows(copied)
        self._last_loaded_updated_at = self._max_updated_at(copied)

    def _merge_rows(self, rows: list[dict[str, Any]]) -> None:
        if self.data is None:
            self.data = []
        data = self.data
        index_by_key: dict[str, int] = {}
        for index, row in enumerate(data):
            if isinstance(row, dict):
                for key in self._row_keys(row):
                    index_by_key[key] = index

        for incoming in rows:
            matched_index = None
            for key in self._row_keys(incoming):
                if key in index_by_key:
                    matched_index = index_by_key[key]
                    break
            if self._is_inactive_status(incoming):
                if matched_index is not None:
                    data.pop(matched_index)
                    index_by_key = {}
                    for index, row in enumerate(data):
                        if isinstance(row, dict):
                            for key in self._row_keys(row):
                                index_by_key[key] = index
                continue
            if matched_index is None:
                data.append(deepcopy(incoming))
            else:
                data[matched_index] = deepcopy(incoming)

        self._snapshot = self._build_snapshot(data)
        self._snapshot_rows = self._build_snapshot_rows(data)
        self._last_loaded_updated_at = max(self._max_updated_at(data), self._max_updated_at(rows))

    @staticmethod
    def _configured_page_size() -> int:
        value = getenv("NAV_API_TASK_PAGE_SIZE", "500").strip()
        if not value:
            return 500
        try:
            parsed = int(value)
        except ValueError:
            return 500
        return max(1, min(parsed, 1000))

    @staticmethod
    def _max_updated_at(rows: list[dict[str, Any]]) -> str:
        values = [str(row.get("updated_at") or "") for row in rows if isinstance(row, dict) and row.get("updated_at")]
        return max(values) if values else ""

    @staticmethod
    def _is_inactive_status(row: dict[str, Any]) -> bool:
        return str(row.get("status") or "").strip().lower() in {"completed", "archived", "cancelled"}

    @classmethod
    def _row_keys(cls, row: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        for field in ("db_task_id", "trip_number", "google_sheet_row", "index"):
            value = row.get(field)
            if value is not None and str(value).strip() != "":
                keys.append(f"{field}:{value}")
        if not keys:
            keys.append(f"object:{id(row)}")
        return keys

    @classmethod
    def _row_key(cls, row: dict[str, Any]) -> str:
        return cls._row_keys(row)[0]

    @classmethod
    def _build_snapshot(cls, rows: list[dict]) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            fingerprint = cls._row_fingerprint(row)
            for key in cls._row_keys(row):
                snapshot[key] = fingerprint
        return snapshot

    @classmethod
    def _build_snapshot_rows(cls, rows: list[dict]) -> dict[str, dict[str, Any]]:
        snapshot: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = cls._normalized_row(row)
            for key in cls._row_keys(row):
                snapshot[key] = normalized
        return snapshot

    @classmethod
    def _snapshot_fingerprint_for_row(cls, snapshot: dict[str, str], row: dict[str, Any]) -> str | None:
        for key in cls._row_keys(row):
            found = snapshot.get(key)
            if found is not None:
                return found
        return None

    @classmethod
    def _row_fingerprint(cls, row: dict[str, Any]) -> str:
        return json.dumps(cls._normalized_row(row), ensure_ascii=False, sort_keys=True, default=str)

    @classmethod
    def _normalized_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        normalized = {key: value
                      for key, value in row.items()
                      if key not in cls._FINGERPRINT_IGNORED_FIELDS}

        google_row = normalized.get("google_sheet_row") or normalized.get("index")
        if google_row is not None and str(google_row).strip() != "":
            normalized.pop("google_sheet_row", None)
            normalized.pop("index", None)
            normalized["_google_sheet_row"] = cls._normalize_scalar(google_row)
        if isinstance(normalized.get("processed"), list):
            normalized["processed"] = [bool(value) for value in normalized["processed"]]
        normalized["status"] = str(normalized.get("status") or "active")
        return normalized

    @classmethod
    def _changed_fields(cls, snapshot_rows: dict[str, dict[str, Any]], row: dict[str, Any]) -> set[str]:
        old = None
        for key in cls._row_keys(row):
            if key in snapshot_rows:
                old = snapshot_rows[key]
                break
        new = cls._normalized_row(row)
        if old is None:
            return {"<new_or_unmatched>"}
        changed = set()
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                changed.add(key)
        return changed

    @classmethod
    def _row_diff_summary(cls, snapshot_rows: dict[str, dict[str, Any]],
                          row: dict[str, Any],
                          changed_fields: set[str] | None = None, ) -> str:
        matched_key = None
        for key in cls._row_keys(row):
            if key in snapshot_rows:
                matched_key = key
                break
        if matched_key is None:
            return f"{cls._row_key(row)} new_or_unmatched"
        changed = sorted(changed_fields if changed_fields is not None else cls._changed_fields(snapshot_rows, row))
        return f"{matched_key}: {', '.join(changed[:12])}"

    @staticmethod
    def _normalize_scalar(value: Any) -> Any:
        try:
            text = str(value).strip()
            if text and text.isdigit():
                return int(text)
        except Exception:
            pass
        return value

    @staticmethod
    def _row_identity_int(row: dict[str, Any]) -> int | None:
        value = row.get("trip_number") or row.get("google_sheet_row") or row.get("index")
        try:
            if value is None or str(value).strip() == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
