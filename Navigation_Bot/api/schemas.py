from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskUpsertRequest(BaseModel):
    row: dict[str, Any]
    source: str = "api"
    source_key: str = ""


class TaskBatchUpsertRequest(BaseModel):
    rows: list[dict[str, Any]]
    source: str = "api"
    source_key: str = ""


class TaskBatchCompleteRequest(BaseModel):
    row_identities: list[int]
    source: str = "api"
    source_key: str = ""


class TaskCompleteRequest(BaseModel):
    source: str = "api"
    source_key: str = ""


class RegistryEntryRequest(BaseModel):
    entry: dict[str, Any]


class NoteCreateRequest(BaseModel):
    text: str
    author: str = "api"
    media_type: str = ""
    media_paths: list[str] = Field(default_factory=list)
    is_important: bool = False
    created_at: str | None = None


class NavigationSnapshotRequest(BaseModel):
    vehicle_plate: str | None = None
    vehicle_monitoring_id: int | None = None
    coordinates: str = ""
    geo_text: str = ""
    geo_zona: str = ""
    speed_kmh: float | None = None
    gps_fix_text: str = ""
    gps_fix_age_seconds: int | None = None
    has_fresh_coordinates: bool = False
    is_navigation_stale: bool = False
    collected_at: str | None = None


class HistoryItemRequest(BaseModel):
    item: dict[str, Any]


class HistoryBatchRequest(BaseModel):
    items: list[dict[str, Any]]


class NoteBatchCreateRequest(BaseModel):
    items: list[NoteCreateRequest]


class NavigationSnapshotBatchRequest(BaseModel):
    items: list[NavigationSnapshotRequest]


class UserCreateRequest(BaseModel):
    username: str
    display_name: str = ""
    role: str = "viewer"
    is_active: bool = True


class ApiKeyCreateRequest(BaseModel):
    name: str = ""
    expires_at: str | None = None

    @field_validator("expires_at", mode="before")
    @classmethod
    def normalize_expires_at(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value or value.lower() in {"null", "none", "string"}:
                return None
        return value
