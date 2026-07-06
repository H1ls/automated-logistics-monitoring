from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from Navigation_Bot.core.infrastructure.api.dependencies import postgres_connection, require_roles
from Navigation_Bot.core.repositories.postgres_audit_repository import PostgresAuditRepository
from Navigation_Bot.core.repositories.postgres_task_repository import PostgresTaskRepository
from Navigation_Bot.core.repositories.postgres_task_reader import PostgresTaskReader
from Navigation_Bot.core.repositories.postgres_vehicle_repository import PostgresVehicleRepository
from Navigation_Bot.core.repositories.postgres_task_writer import PostgresTaskWriter, TaskConflictError
from Navigation_Bot.core.repositories.postgres_user_repository import PostgresUserRepository
from Navigation_Bot.core.storage.postgres_connection import postgres_healthcheck
from Navigation_Bot.core.application.services.postgres_history_services import (PostgresNavigationHistoryService,
                                                                                PostgresNoteHistoryService,
                                                                                PostgresRouteEstimateHistoryService,
                                                                                PostgresStatusEventService, )
from Navigation_Bot.core.infrastructure.api.schemas import (ApiKeyCreateRequest,
                                                            HistoryBatchRequest,
                                                            HistoryItemRequest,
                                                            LoginRequest,
                                                            NavigationSnapshotBatchRequest,
                                                            NavigationSnapshotRequest,
                                                            NoteBatchCreateRequest,
                                                            NoteCreateRequest,
                                                            TaskBatchCompleteRequest,
                                                            RegistryEntryRequest,
                                                            TaskBatchUpsertRequest,
                                                            TaskCompleteRequest,
                                                            TaskUpsertRequest,
                                                            UserCreateRequest,
                                                            UserUpdateRequest, )

router = APIRouter()

Connection = Annotated[Any, Depends(postgres_connection)]
ReadAccess = Annotated[dict[str, Any], Depends(require_roles("admin", "dispatcher", "viewer"))]
WriteAccess = Annotated[dict[str, Any], Depends(require_roles("admin", "dispatcher"))]
AdminAccess = Annotated[dict[str, Any], Depends(require_roles("admin"))]


def _conflict_detail(exc: TaskConflictError) -> dict[str, Any]:
    return {
        "error": "task_conflict",
        "task_id": exc.task_id,
        "expected_updated_at": str(exc.expected_updated_at) if exc.expected_updated_at is not None else None,
        "current_updated_at": str(exc.current_updated_at) if exc.current_updated_at is not None else None,
    }


def _user_source(user: dict[str, Any]) -> str:
    return str(user.get("username") or "api")


def _audit(connection: Connection) -> PostgresAuditRepository:
    return PostgresAuditRepository(connection)


def _item_with_trip_number(item: dict[str, Any], trip_number: int, user: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row["trip_number"] = trip_number
    if "source" not in row:
        row["source"] = _user_source(user)
    if "user_id" not in row:
        row["user_id"] = user.get("id")
    return row


def _batch_result(count: int, skipped: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"ok": True, "count": count, "skipped": skipped or []}


def _gui_session_expires_at() -> str:
    try:
        hours = int(os.getenv("NAV_GUI_SESSION_HOURS", "12"))
    except ValueError:
        hours = 12
    hours = min(max(hours, 1), 168)
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _task_before_from_row(audit: PostgresAuditRepository, row: dict[str, Any]) -> dict[str, Any] | None:
    task_id = row.get("db_task_id") or row.get("task_id")
    try:
        if task_id:
            return audit.task_snapshot(int(task_id))
    except (TypeError, ValueError):
        pass
    trip_number = row.get("trip_number")
    try:
        if trip_number:
            return audit.task_snapshot(trip_number=int(trip_number))
    except (TypeError, ValueError):
        pass
    return None


@router.get("/me")
def get_me(user: ReadAccess) -> dict[str, Any]:
    return {"user": user}


@router.post("/auth/login")
def login(payload: LoginRequest, connection: Connection) -> dict[str, Any]:
    repository = PostgresUserRepository(connection)
    user = repository.authenticate(payload.username, payload.password)
    bootstrapped = False
    if not user and not repository.has_active_password_users():
        try:
            user = repository.create_user(username=payload.username,
                                          display_name=payload.username,
                                          password=payload.password,
                                          role="admin",
                                          is_active=True)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        bootstrapped = True
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    session_name = "GUI session"
    repository.revoke_user_api_keys_by_name(user["id"], session_name)
    api_key = repository.create_api_key(user_id=user["id"],
                                        name=session_name,
                                        expires_at=_gui_session_expires_at())
    return {"ok": True, "user": user, "api_key": api_key["api_key"], "bootstrapped": bootstrapped}


@router.get("/users")
def list_users(connection: Connection, _user: AdminAccess) -> dict[str, Any]:
    rows = PostgresUserRepository(connection).list_users()
    return {"count": len(rows), "items": rows}


@router.get("/audit-log")
def list_audit_log(connection: Connection,
                   _user: AdminAccess,
                   entity_type: str = Query(default=""),
                   entity_id: int | None = Query(default=None),
                   user_id: int | None = Query(default=None),
                   limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    rows = _audit(connection).list_entries(entity_type=entity_type,
                                           entity_id=entity_id,
                                           user_id=user_id,
                                           limit=limit)
    return {"count": len(rows), "items": rows}


@router.post("/users")
def create_user(payload: UserCreateRequest, connection: Connection, user: AdminAccess) -> dict[str, Any]:
    try:
        created_user = PostgresUserRepository(connection).create_user(username=payload.username,
                                                                      display_name=payload.display_name,
                                                                      password=payload.password,
                                                                      role=payload.role,
                                                                      is_active=payload.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _audit(connection).record(user=user,
                              entity_type="app_users",
                              entity_id=created_user["id"],
                              action="create_or_update",
                              after_data=created_user)

    return {"ok": True, "user": created_user}


@router.put("/users/{user_id}")
def update_user(user_id: int,
                payload: UserUpdateRequest,
                connection: Connection,
                user: AdminAccess) -> dict[str, Any]:
    try:
        updated_user = PostgresUserRepository(connection).update_user(user_id,
                                                                      username=payload.username,
                                                                      display_name=payload.display_name,
                                                                      password=payload.password,
                                                                      role=payload.role,
                                                                      is_active=payload.is_active)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "user_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc

    _audit(connection).record(user=user,
                              entity_type="app_users",
                              entity_id=updated_user["id"],
                              action="update",
                              after_data=updated_user)
    return {"ok": True, "user": updated_user}


@router.post("/users/{user_id}/api-keys")
def create_user_api_key(user_id: int,
                        payload: ApiKeyCreateRequest,
                        connection: Connection,
                        user: AdminAccess, ) -> dict[str, Any]:
    try:
        api_key = PostgresUserRepository(connection).create_api_key(user_id=user_id,
                                                                    name=payload.name,
                                                                    expires_at=payload.expires_at)

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_data = {key: value for key, value in api_key.items() if key != "api_key"}

    _audit(connection).record(user=user,
                              entity_type="api_keys",
                              entity_id=api_key["id"],
                              action="create",
                              after_data=audit_data)

    return {"ok": True, "api_key": api_key}


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int, connection: Connection, user: AdminAccess) -> dict[str, Any]:
    if not PostgresUserRepository(connection).revoke_api_key(key_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api_key_not_found")
    _audit(connection).record(user=user,
                              entity_type="api_keys",
                              entity_id=key_id,
                              action="revoke")

    return {"ok": True, "api_key_id": key_id}


@router.get("/health")
def health(connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    info = postgres_healthcheck(connection=connection)
    return {"ok": True, "database": info}


@router.get("/tasks")
def list_tasks(connection: Connection,
               _user: ReadAccess,
               response: Response,
               source_key: str = Query(default=""),
               strict_source_key: bool = Query(default=False),
               limit: int | None = Query(default=None, ge=1, le=1000),
               offset: int = Query(default=0, ge=0),
               updated_since: str | None = Query(default=None),
               include_completed: bool = Query(default=False),
               date_from: str | None = Query(default=None),
               date_to: str | None = Query(default=None),
               full: bool = Query(default=False)) -> dict[str, Any]:
    if limit is not None or updated_since:
        reader = PostgresTaskReader(connection)
        rows, total = reader.load_active_rows_page(source_key,
                                                   include_null_source=not strict_source_key,
                                                   limit=limit or 100,
                                                   offset=offset,
                                                   updated_since=updated_since,
                                                   include_completed=include_completed,
                                                   date_from=date_from,
                                                   date_to=date_to)
        next_offset = offset + len(rows)
        return {"count": len(rows),
                "total": total,
                "items": rows,
                "limit": limit or 100,
                "offset": offset,
                "next_offset": next_offset if next_offset < total else None}

    if not full:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tasks_query_requires_limit_updated_since_or_full_true",
        )

    if strict_source_key and source_key:
        rows = PostgresTaskReader(connection).load_active_rows(source_key, include_null_source=False)
        return {"count": len(rows), "items": rows, "full": True}

    repository = PostgresTaskRepository(connection)
    if source_key:
        repository.set_source_key(source_key)
    else:
        repository.reload()
    rows = repository.get()
    return {"count": len(rows), "items": rows, "full": True}


@router.post("/tasks")
def upsert_task(payload: TaskUpsertRequest, connection: Connection, user: WriteAccess) -> dict[str, Any]:
    repository = PostgresTaskRepository(connection)
    if payload.source_key:
        repository.set_source_key(payload.source_key)
    audit = _audit(connection)
    before = _task_before_from_row(audit, payload.row)
    try:
        result = repository.upsert_from_row(payload.row, source=_user_source(user))
    except TaskConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_conflict_detail(exc)) from exc

    if result is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_task_row")
    after = audit.task_snapshot(result["task_id"])
    audit.record(user=user,
                 entity_type="tasks",
                 entity_id=result["task_id"],
                 action="create" if before is None else "update",
                 before_data=before,
                 after_data=after)

    return {"ok": True, **result}


@router.post("/tasks/batch")
def upsert_tasks_batch(payload: TaskBatchUpsertRequest, connection: Connection, user: WriteAccess) -> dict[str, Any]:
    repository = PostgresTaskRepository(connection)
    if payload.source_key:
        repository.set_source_key(payload.source_key)
    audit = _audit(connection)
    results = []
    try:
        for row_number, row in enumerate(payload.rows, start=1):
            if not isinstance(row, dict):
                continue
            result = repository.upsert_from_row(row, source=_user_source(user))
            if result is not None:
                results.append(result)
                audit.record_compact(user=user,
                                     entity_type="tasks",
                                     entity_id=result["task_id"],
                                     action="create" if result.get("created") else "update",
                                     summary={"batch": True,
                                              "row_number": row_number,
                                              "trip_number": result.get("trip_number")})

    except TaskConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_conflict_detail(exc)) from exc
    return {"ok": True, "count": len(results), "items": results}


@router.post("/tasks/complete/batch")
def complete_tasks_batch(payload: TaskBatchCompleteRequest,
                         connection: Connection,
                         user: WriteAccess) -> dict[str, Any]:
    writer = PostgresTaskWriter(connection, payload.source_key)
    audit = _audit(connection)
    completed = []
    skipped = []
    for row_identity in payload.row_identities:
        try:
            parsed_identity = int(row_identity)
        except (TypeError, ValueError):
            skipped.append({"row_identity": row_identity, "reason": "invalid_row_identity"})
            continue
        if not writer.mark_task_completed(parsed_identity, source=_user_source(user)):
            skipped.append({"row_identity": parsed_identity, "reason": "task_not_found"})
            continue
        completed.append(parsed_identity)
        audit.record_compact(user=user,
                             entity_type="tasks",
                             action="complete",
                             summary={"batch": True, "row_identity": parsed_identity})
    return {"ok": True, "count": len(completed), "items": completed, "skipped": skipped}


@router.post("/tasks/{row_identity}/complete")
def complete_task(row_identity: int, payload: TaskCompleteRequest, connection: Connection, user: WriteAccess) -> dict[
    str, Any]:
    writer = PostgresTaskWriter(connection, payload.source_key)
    audit = _audit(connection)
    before = audit.task_snapshot(trip_number=row_identity)
    if not writer.mark_task_completed(row_identity, source=_user_source(user)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task_not_found")
    after = audit.task_snapshot(trip_number=row_identity)
    audit.record(user=user,
                 entity_type="tasks",
                 entity_id=after.get("id") if after else None, action="complete",
                 before_data=before,
                 after_data=after)

    return {"ok": True, "row_identity": row_identity}


@router.get("/tasks/{trip_number}/notes")
def list_task_notes(trip_number: int, connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    rows = PostgresNoteHistoryService(connection).get_by_trip_number(trip_number)
    return {"count": len(rows), "items": rows}


@router.post("/tasks/{trip_number}/notes")
def add_task_note(trip_number: int, payload: NoteCreateRequest, connection: Connection, user: WriteAccess) -> dict[
    str, Any]:
    item = payload.model_dump()
    item["trip_number"] = trip_number
    item["author"] = _user_source(user)
    item["author_user_id"] = user.get("id")
    PostgresNoteHistoryService(connection).append(item)
    _audit(connection).record(user=user, entity_type="task_notes", entity_id=None, action="create", after_data=item)
    return {"ok": True}


@router.post("/tasks/{trip_number}/notes/batch")
def add_task_notes_batch(trip_number: int,
                         payload: NoteBatchCreateRequest,
                         connection: Connection,
                         user: WriteAccess) -> dict[str, Any]:
    service = PostgresNoteHistoryService(connection)
    for note in payload.items:
        item = note.model_dump()
        item["trip_number"] = trip_number
        item["author"] = _user_source(user)
        item["author_user_id"] = user.get("id")
        service.append(item)
    _audit(connection).record_compact(user=user,
                                     entity_type="task_notes",
                                     action="batch_create",
                                     summary={"trip_number": trip_number, "count": len(payload.items)})
    return _batch_result(len(payload.items))


@router.get("/tasks/{trip_number}/status-events")
def list_task_status_events(trip_number: int, connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    rows = PostgresStatusEventService(connection).get_by_trip_number(trip_number)
    return {"count": len(rows), "items": rows}


@router.post("/tasks/{trip_number}/status-events")
def add_task_status_event(trip_number: int, payload: HistoryItemRequest, connection: Connection, user: WriteAccess) -> \
        dict[str, Any]:
    item = dict(payload.item)
    item["trip_number"] = trip_number
    item["source"] = _user_source(user)
    item["user_id"] = user.get("id")
    PostgresStatusEventService(connection).append(item)
    _audit(connection).record(user=user, entity_type="status_events", entity_id=None, action="create", after_data=item)
    return {"ok": True}


@router.post("/tasks/{trip_number}/status-events/batch")
def add_task_status_events_batch(trip_number: int,
                                 payload: HistoryBatchRequest,
                                 connection: Connection,
                                 user: WriteAccess) -> dict[str, Any]:
    service = PostgresStatusEventService(connection)
    for item in payload.items:
        service.append(_item_with_trip_number(item, trip_number, user))
    _audit(connection).record_compact(user=user,
                                     entity_type="status_events",
                                     action="batch_create",
                                     summary={"trip_number": trip_number, "count": len(payload.items)})
    return _batch_result(len(payload.items))


@router.get("/tasks/{trip_number}/route-estimates")
def list_task_route_estimates(trip_number: int, connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    rows = PostgresRouteEstimateHistoryService(connection).get_by_trip_number(trip_number)
    return {"count": len(rows), "items": rows}


@router.post("/tasks/{trip_number}/route-estimates")
def add_task_route_estimate(trip_number: int, payload: HistoryItemRequest, connection: Connection, user: WriteAccess) -> \
        dict[str, Any]:
    item = dict(payload.item)
    item["trip_number"] = trip_number
    PostgresRouteEstimateHistoryService(connection).append(item)
    _audit(connection).record(user=user,entity_type="route_estimates",entity_id=None,action="create",after_data=item)
    return {"ok": True}


@router.post("/tasks/{trip_number}/route-estimates/batch")
def add_task_route_estimates_batch(trip_number: int,
                                   payload: HistoryBatchRequest,
                                   connection: Connection,
                                   user: WriteAccess) -> dict[str, Any]:
    service = PostgresRouteEstimateHistoryService(connection)
    for item in payload.items:
        row = dict(item)
        row["trip_number"] = trip_number
        service.append(row)
    _audit(connection).record_compact(user=user,
                                     entity_type="route_estimates",
                                     action="batch_create",
                                     summary={"trip_number": trip_number, "count": len(payload.items)})
    return _batch_result(len(payload.items))


@router.get("/tasks/{trip_number}/navigation")
def list_task_navigation(trip_number: int, connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    rows = PostgresNavigationHistoryService(connection).get_by_trip_number(trip_number)
    return {"count": len(rows), "items": rows}


@router.post("/tasks/{trip_number}/navigation")
def add_task_navigation(trip_number: int, payload: NavigationSnapshotRequest, connection: Connection,
                        user: WriteAccess) -> dict[str, Any]:
    item = payload.model_dump()
    item["trip_number"] = trip_number
    PostgresNavigationHistoryService(connection).append(item)
    _audit(connection).record(user=user,entity_type="vehicle_navigation_history",entity_id=None,action="create",after_data=item)
    return {"ok": True}


@router.post("/tasks/{trip_number}/navigation/batch")
def add_task_navigation_batch(trip_number: int,
                              payload: NavigationSnapshotBatchRequest,
                              connection: Connection,
                              user: WriteAccess) -> dict[str, Any]:
    service = PostgresNavigationHistoryService(connection)
    for snapshot in payload.items:
        item = snapshot.model_dump()
        item["trip_number"] = trip_number
        service.append(item)
    _audit(connection).record_compact(user=user,
                                     entity_type="vehicle_navigation_history",
                                     action="batch_create",
                                     summary={"trip_number": trip_number, "count": len(payload.items)})
    return _batch_result(len(payload.items))


@router.get("/vehicles")
def list_vehicles(connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    rows = PostgresVehicleRepository(connection).list_registry_entries()
    return {"count": len(rows), "items": rows}


@router.post("/vehicles")
def upsert_vehicle(payload: RegistryEntryRequest, connection: Connection, user: WriteAccess) -> dict[str, Any]:
    audit = _audit(connection)
    before = None
    raw_vehicle_id = payload.entry.get("vehicle_id") or payload.entry.get("_db_vehicle_id")
    try:
        before = audit.vehicle_snapshot(int(raw_vehicle_id)) if raw_vehicle_id else None
    except (TypeError, ValueError):
        before = None
    vehicle_id = PostgresVehicleRepository(connection).upsert_registry_entry(payload.entry)
    if vehicle_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_vehicle_entry")
    after = audit.vehicle_snapshot(vehicle_id)
    audit.record(user=user,
                 entity_type="vehicles",
                 entity_id=vehicle_id,
                 action="create" if before is None else "update",
                 before_data=before,after_data=after)
    return {"ok": True, "vehicle_id": vehicle_id}


@router.get("/vehicles/{monitoring_id}/navigation")
def list_vehicle_navigation(monitoring_id: int, connection: Connection, _user: ReadAccess) -> dict[str, Any]:
    rows = PostgresNavigationHistoryService(connection).get_by_vehicle_monitoring_id(monitoring_id)
    return {"count": len(rows), "items": rows}
