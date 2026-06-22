from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Navigation_Bot.core.storage.postgres_connection import connect_postgres


@dataclass(slots=True)
class RequestStat:
    name: str
    elapsed_ms: float
    ok: bool
    status_code: int | None = None
    error: str = ""


@dataclass(slots=True)
class SmokeResult:
    stats: list[RequestStat] = field(default_factory=list)

    def extend(self, items: list[RequestStat]) -> None:
        self.stats.extend(items)


class SmokeClient:
    def __init__(self, *, base_url: str, api_key: str, timeout: float, client_id: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = client_id
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})

    def run(self, *, iterations: int, batch_size: int, complete: bool, update_existing: bool, reuse_rows: bool,
            source_key: str, page_limit: int,) -> list[RequestStat]:

        stats: list[RequestStat] = []
        for iteration in range(iterations):
            params = {"source_key": source_key, "strict_source_key": "true"} if source_key else {}
            params["limit"] = page_limit
            params["offset"] = 0
            tasks_payload, stat = self._request("GET /tasks", "GET", "/api/v1/tasks", params=params or None)
            stats.append(stat)

            rows = self._build_task_rows(tasks_payload,
                                         iteration,
                                         batch_size,
                                         reuse_rows=reuse_rows,
                                         source_key=source_key,
                                         update_existing=update_existing)
            _, stat = self._request("POST /tasks/batch",
                                    "POST",
                                    "/api/v1/tasks/batch",
                                    json={"rows": rows, "source": "load_smoke", "source_key": source_key})
            stats.append(stat)

            if complete:
                identities = [int(row["trip_number"]) for row in rows if row.get("trip_number")]
                _, stat = self._request("POST /tasks/complete/batch",
                                        "POST",
                                        "/api/v1/tasks/complete/batch",
                                        json={"row_identities": identities,
                                              "source": "load_smoke",
                                              "source_key": source_key})
                stats.append(stat)
        return stats

    def cleanup_generated(self, *, clients: int, iterations: int, batch_size: int) -> list[RequestStat]:
        stats: list[RequestStat] = []
        identities = self._generated_identities(clients=clients,
                                                iterations=iterations,
                                                batch_size=batch_size)
        for offset in range(0, len(identities), 500):
            chunk = identities[offset:offset + 500]
            _, stat = self._request("POST /tasks/complete/batch",
                                    "POST",
                                    "/api/v1/tasks/complete/batch",
                                    json={"row_identities": chunk, "source": "load_smoke_cleanup", "source_key": ""})
            stats.append(stat)
        return stats

    def purge_generated(self,
                        *,
                        clients: int,
                        iterations: int,
                        batch_size: int,
                        source_key: str) -> tuple[list[RequestStat], int, int, int, int, int, int]:
        identities = self._generated_identities(clients=clients,
                                                iterations=iterations,
                                                batch_size=batch_size)
        identities.append(self._incremental_check_trip_number())
        identities = sorted(set(identities))
        stats: list[RequestStat] = []
        purged_tasks = 0
        purged_audit_rows = 0
        with connect_postgres() as connection:
            route_points_before = self._count_smoke_route_points(connection)
            audit_before = self._count_smoke_audit_rows(connection)
            for offset in range(0, len(identities), 500):
                chunk = identities[offset:offset + 500]
                started = time.perf_counter()
                try:
                    chunk_text = [str(value) for value in chunk]
                    task_rows = connection.execute(
                        """
                        SELECT id
                        FROM tasks
                        WHERE trip_number = ANY(%(trip_numbers)s)
                          AND (
                              google_worksheet_title = %(source_key)s
                              OR raw_load = 'Smoke load'
                              OR raw_unload = 'Smoke unload'
                              OR comm_unload LIKE 'load_smoke%%'
                              OR completion_source IN ('load_smoke', 'load_smoke_cleanup')
                          )
                        """,
                        {"trip_numbers": chunk, "source_key": source_key},
                    ).fetchall()
                    task_ids = [int(row["id"]) for row in task_rows]
                    audit_rows = connection.execute(
                        """
                        DELETE FROM audit_log
                        WHERE entity_type = 'tasks'
                          AND (
                              entity_id = ANY(%(task_ids)s)
                              OR changed_fields ->> 'trip_number' = ANY(%(trip_numbers)s)
                              OR changed_fields ->> 'row_identity' = ANY(%(trip_numbers)s)
                          )
                        RETURNING id
                        """,
                        {"task_ids": task_ids or [-1], "trip_numbers": chunk_text},
                    ).fetchall()
                    purged_audit_rows += len(audit_rows)

                    rows = connection.execute(
                        """
                        DELETE FROM tasks
                        WHERE trip_number = ANY(%(trip_numbers)s)
                          AND (
                              google_worksheet_title = %(source_key)s
                              OR raw_load = 'Smoke load'
                              OR raw_unload = 'Smoke unload'
                              OR comm_unload LIKE 'load_smoke%%'
                              OR completion_source IN ('load_smoke', 'load_smoke_cleanup')
                          )
                        RETURNING id
                        """,
                        {"trip_numbers": chunk, "source_key": source_key},
                    ).fetchall()
                    purged_tasks += len(rows)
                    stats.append(RequestStat(name="DELETE smoke tasks",
                                             elapsed_ms=(time.perf_counter() - started) * 1000,
                                             ok=True))
                except Exception as exc:
                    stats.append(RequestStat(name="DELETE smoke tasks",
                                             elapsed_ms=(time.perf_counter() - started) * 1000,
                                             ok=False,
                                             error=str(exc)))
            purged_audit_rows += self._delete_remaining_smoke_audit_rows(connection)
            route_points_after = self._count_smoke_route_points(connection)
            audit_after = self._count_smoke_audit_rows(connection)
        return stats, purged_tasks, purged_audit_rows, route_points_before, route_points_after, audit_before, audit_after

    def incremental_check(self, *, source_key: str) -> list[RequestStat]:
        stats: list[RequestStat] = []
        trip_number = self._incremental_check_trip_number()
        row = self._smoke_row(trip_number=trip_number,
                              iteration=0,
                              row_slot=0,
                              source_key=source_key)
        _, stat = self._request("POST /tasks/batch",
                                "POST",
                                "/api/v1/tasks/batch",
                                json={"rows": [row],
                                      "source": "load_smoke_incremental",
                                      "source_key": source_key})
        stats.append(stat)
        if not stat.ok:
            return stats

        page, stat = self._request("GET /tasks",
                                   "GET",
                                   "/api/v1/tasks",
                                   params={"source_key": source_key,
                                           "strict_source_key": "true",
                                           "limit": 100,
                                           "offset": 0})
        stats.append(stat)
        baseline = self._updated_at_for_trip(page, trip_number)
        stats.append(
            self._check_stat("CHECK incremental baseline", bool(baseline), "created smoke row was not returned"))
        if not baseline:
            return stats

        time.sleep(0.05)
        updated = dict(row)
        updated["updated_at"] = baseline
        updated["comm_unload"] = f"load_smoke incremental update {time.time_ns()}"
        payload, stat = self._request("POST /tasks/batch",
                                      "POST",
                                      "/api/v1/tasks/batch",
                                      json={"rows": [updated],
                                            "source": "load_smoke_incremental",
                                            "source_key": source_key})
        stats.append(stat)
        if not stat.ok:
            return stats

        incremental, stat = self._request("GET /tasks incremental",
                                          "GET",
                                          "/api/v1/tasks",
                                          params={"source_key": source_key,
                                                  "strict_source_key": "true",
                                                  "limit": 100,
                                                  "updated_since": baseline})
        stats.append(stat)
        active_row = self._row_for_trip(incremental, trip_number)
        stats.append(self._check_stat("CHECK incremental update",
                                      bool(active_row and str(active_row.get("status") or "") == "active"),
                                      "updated active row was not returned by updated_since"))

        item = None
        if isinstance(payload, dict):
            items = [value for value in payload.get("items", []) if isinstance(value, dict)]
            item = items[0] if items else None
        complete_since = str((item or {}).get("updated_at") or (active_row or {}).get("updated_at") or baseline)
        time.sleep(0.05)
        _, stat = self._request("POST /tasks/complete/batch",
                                "POST",
                                "/api/v1/tasks/complete/batch",
                                json={"row_identities": [trip_number],
                                      "source": "load_smoke_incremental",
                                      "source_key": source_key})
        stats.append(stat)
        if not stat.ok:
            return stats

        completed, stat = self._request("GET /tasks incremental",
                                        "GET",
                                        "/api/v1/tasks",
                                        params={"source_key": source_key,
                                                "strict_source_key": "true",
                                                "limit": 100,
                                                "updated_since": complete_since})
        stats.append(stat)
        completed_row = self._row_for_trip(completed, trip_number)
        stats.append(self._check_stat("CHECK incremental complete",
                                      bool(completed_row and str(completed_row.get("status") or "") == "completed"),
                                      "completed row was not returned by updated_since"))
        return stats

    def _request(self, name: str, method: str, path: str, **kwargs: Any) -> tuple[Any, RequestStat]:
        started = time.perf_counter()
        status_code = None
        try:
            response = self.session.request(method,
                                            f"{self.base_url}{path}",
                                            timeout=self.timeout,
                                            **kwargs)
            status_code = response.status_code
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            payload = response.json() if response.content else None
            return payload, RequestStat(name=name, elapsed_ms=elapsed_ms, ok=True, status_code=status_code)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return None, RequestStat(name=name,
                                     elapsed_ms=elapsed_ms,
                                     ok=False,
                                     status_code=status_code,
                                     error=str(exc))

    @staticmethod
    def _generated_identities(*, clients: int, iterations: int, batch_size: int) -> list[int]:
        identities: list[int] = []
        for client_id in range(1, max(1, clients) + 1):
            for iteration in range(max(1, iterations)):
                for row_slot in range(max(1, batch_size)):
                    identities.append(900000000 + client_id * 100000 + iteration * 100 + row_slot)
                    identities.append(900000000 + client_id * 100000 + row_slot)
        return sorted(set(identities))

    @staticmethod
    def _count_smoke_route_points(connection: Any) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM route_points
            WHERE location IN ('Smoke load', 'Smoke unload')
               OR comment LIKE 'load_smoke%%'
            """
        ).fetchone()
        return int(row["count"] or 0)

    @staticmethod
    def _count_smoke_audit_rows(connection: Any) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM audit_log al
            WHERE al.entity_type = 'tasks'
              AND (
                  al.changed_fields::text LIKE '%%load_smoke%%'
                  OR al.changed_fields::text LIKE '%%900%%'
                  OR EXISTS (
                      SELECT 1
                      FROM tasks t
                      WHERE t.id = al.entity_id
                        AND (
                            t.google_worksheet_title = 'load_smoke'
                            OR t.raw_load = 'Smoke load'
                            OR t.raw_unload = 'Smoke unload'
                            OR t.comm_unload LIKE 'load_smoke%%'
                            OR t.completion_source IN ('load_smoke', 'load_smoke_cleanup')
                        )
                  )
              )
            """
        ).fetchone()
        return int(row["count"] or 0)

    @staticmethod
    def _delete_remaining_smoke_audit_rows(connection: Any) -> int:
        rows = connection.execute(
            """
            DELETE FROM audit_log al
            WHERE al.entity_type = 'tasks'
              AND (
                  al.changed_fields::text LIKE '%%load_smoke%%'
                  OR al.changed_fields::text LIKE '%%900%%'
                  OR EXISTS (
                      SELECT 1
                      FROM tasks t
                      WHERE t.id = al.entity_id
                        AND (
                            t.google_worksheet_title = 'load_smoke'
                            OR t.raw_load = 'Smoke load'
                            OR t.raw_unload = 'Smoke unload'
                            OR t.comm_unload LIKE 'load_smoke%%'
                            OR t.completion_source IN ('load_smoke', 'load_smoke_cleanup')
                        )
                  )
              )
            RETURNING id
            """
        ).fetchall()
        return len(rows)

    @staticmethod
    def _incremental_check_trip_number() -> int:
        return 900999001

    @staticmethod
    def _row_for_trip(payload: Any, trip_number: int) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        for row in payload.get("items", []):
            try:
                row_trip_number = int(row.get("trip_number") or 0) if isinstance(row, dict) else 0
            except (TypeError, ValueError):
                row_trip_number = 0
            if isinstance(row, dict) and row_trip_number == trip_number:
                return row
        return None

    @classmethod
    def _updated_at_for_trip(cls, payload: Any, trip_number: int) -> str:
        row = cls._row_for_trip(payload, trip_number)
        return str(row.get("updated_at") or "") if row else ""

    @staticmethod
    def _check_stat(name: str, ok: bool, error: str = "") -> RequestStat:
        return RequestStat(name=name, elapsed_ms=0.0, ok=ok, error="" if ok else error)

    def _build_task_rows(self,
                         tasks_payload: Any,
                         iteration: int,
                         batch_size: int,
                         *,
                         reuse_rows: bool,
                         source_key: str,
                         update_existing: bool) -> list[dict[str, Any]]:
        existing_rows = []
        if isinstance(tasks_payload, dict):
            existing_rows = [row for row in tasks_payload.get("items", []) if isinstance(row, dict)]

        rows: list[dict[str, Any]] = []
        sample = random.sample(existing_rows,
                               k=min(batch_size, len(existing_rows))) if update_existing and existing_rows else []
        for offset, row in enumerate(sample):
            updated = dict(row)
            updated["comm_unload"] = f"load_smoke client={self.client_id} iteration={iteration} row={offset}"
            rows.append(updated)

        while len(rows) < batch_size:
            row_slot = len(rows)
            row_suffix = row_slot if reuse_rows else iteration * 100 + row_slot
            trip_number = 900000000 + self.client_id * 100000 + row_suffix
            rows.append(self._smoke_row(trip_number=trip_number,
                                        iteration=iteration,
                                        row_slot=row_slot,
                                        source_key=source_key))
        return rows

    def _smoke_row(self, *, trip_number: int, iteration: int, row_slot: int, source_key: str) -> dict[str, Any]:
        return {
            "trip_number": trip_number,
            "index": trip_number,
            "google_sheet_row": trip_number,
            "google_worksheet_title": source_key,
            "vehicle_plate": f"SMOKE-{self.client_id:02d}",
            "driver_name": "Load Smoke",
            "driver_phone": "",
            "carrier_name": "Load Smoke",
            "status": "active",
            "loads": [{"sequence": 1, "address": "Smoke load", "date": "", "time": ""}],
            "unloads": [{"sequence": 1, "address": "Smoke unload", "date": "", "time": ""}],
            "processed_unloads": [False],
            "raw_load": "Smoke load",
            "raw_unload": "Smoke unload",
            "comm_load": "",
            "comm_unload": f"load_smoke client={self.client_id} iteration={iteration} row={row_slot}",
        }


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percent)))
    return ordered[index]


def print_summary(stats: list[RequestStat]) -> None:
    names = sorted({stat.name for stat in stats})
    print(f"total requests: {len(stats)}")
    for name in names:
        group = [stat for stat in stats if stat.name == name]
        latencies = [stat.elapsed_ms for stat in group]
        errors = [stat for stat in group if not stat.ok]
        print(
            f"{name}: count {len(group)}, "
            f"p50 {percentile(latencies, 0.50):.0f}ms, "
            f"p95 {percentile(latencies, 0.95):.0f}ms, "
            f"avg {statistics.fmean(latencies):.0f}ms, "
            f"errors {len(errors)}"
        )
        for error in errors[:3]:
            print(f"  error status={error.status_code}: {error.error}")


def p95_by_name(stats: list[RequestStat]) -> dict[str, float]:
    result: dict[str, float] = {}
    for name in sorted({stat.name for stat in stats}):
        latencies = [stat.elapsed_ms for stat in stats if stat.name == name]
        result[name] = percentile(latencies, 0.95)
    return result


def threshold_failures(args: argparse.Namespace, stats: list[RequestStat]) -> list[str]:
    failures: list[str] = []
    errors = [stat for stat in stats if not stat.ok]
    if args.fail_on_errors and errors:
        failures.append(f"errors: {len(errors)}")

    p95_values = p95_by_name(stats)
    if args.max_p95_ms > 0:
        for name, value in p95_values.items():
            if value > args.max_p95_ms:
                failures.append(f"{name} p95 {value:.0f}ms > {args.max_p95_ms:.0f}ms")
    if args.max_get_p95_ms > 0:
        value = p95_values.get("GET /tasks", 0.0)
        if value > args.max_get_p95_ms:
            failures.append(f"GET /tasks p95 {value:.0f}ms > {args.max_get_p95_ms:.0f}ms")
    if args.max_batch_p95_ms > 0:
        value = p95_values.get("POST /tasks/batch", 0.0)
        if value > args.max_batch_p95_ms:
            failures.append(f"POST /tasks/batch p95 {value:.0f}ms > {args.max_batch_p95_ms:.0f}ms")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel API smoke test for Navigation Bot.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--complete", action="store_true",
                        help="Also call /tasks/complete/batch for generated/updated rows.")
    parser.add_argument("--update-existing", action="store_true",
                        help="Update rows returned by GET /tasks. This can produce expected 409 conflicts under concurrency.")
    parser.add_argument("--reuse-rows", action="store_true",
                        help="Reuse the same smoke trip numbers each iteration instead of growing active tasks.")
    parser.add_argument("--source-key", default="load_smoke",
                        help="Worksheet/source key used to isolate smoke rows from normal task lists.")
    parser.add_argument("--page-limit", type=int, default=100,
                        help="Use paginated GET /tasks with this page size during smoke.")
    parser.add_argument("--cleanup-generated", action="store_true",
                        help="Complete generated smoke trip numbers for the requested clients/iterations/batch-size and exit.")
    parser.add_argument("--purge-generated", action="store_true",
                        help="Delete generated smoke tasks directly from PostgreSQL and cascade-delete their route_points.")
    parser.add_argument("--incremental-check", action="store_true",
                        help="Check that GET /tasks?updated_since returns updated and completed smoke rows.")
    parser.add_argument("--fail-on-errors", action=argparse.BooleanOptionalAction, default=True,
                        help="Exit with code 1 when any request failed.")
    parser.add_argument("--max-p95-ms", type=float, default=0.0,
                        help="Fail if any endpoint p95 exceeds this value. Disabled by default.")
    parser.add_argument("--max-get-p95-ms", type=float, default=0.0,
                        help="Fail if GET /tasks p95 exceeds this value. Disabled by default.")
    parser.add_argument("--max-batch-p95-ms", type=float, default=0.0,
                        help="Fail if POST /tasks/batch p95 exceeds this value. Disabled by default.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = SmokeResult()
    started = time.perf_counter()
    if args.incremental_check:
        client = SmokeClient(base_url=args.base_url,
                             api_key=args.api_key,
                             timeout=args.timeout,
                             client_id=99)
        result.extend(client.incremental_check(source_key=str(args.source_key or "load_smoke")))
        print_summary(result.stats)
        print(f"wall time: {time.perf_counter() - started:.1f}s")
        failures = threshold_failures(args, result.stats)
        if failures:
            print("threshold failures:")
            for failure in failures:
                print(f"  {failure}")
        return 1 if failures else 0

    if args.cleanup_generated or args.purge_generated:
        client = SmokeClient(base_url=args.base_url,
                             api_key=args.api_key,
                             timeout=args.timeout,
                             client_id=0)
        if args.purge_generated:
            stats, purged_tasks, purged_audit_rows, route_points_before, route_points_after, audit_before, audit_after = client.purge_generated(
                clients=args.clients,
                iterations=args.iterations,
                batch_size=args.batch_size,
                source_key=str(args.source_key or ""),
            )
            result.extend(stats)
            print(f"purged tasks: {purged_tasks}")
            print(f"purged audit_log rows: {purged_audit_rows}")
            print(f"smoke route_points: {route_points_before} -> {route_points_after}")
            print(f"smoke audit_log: {audit_before} -> {audit_after}")
        else:
            result.extend(client.cleanup_generated(clients=args.clients,
                                                   iterations=args.iterations,
                                                   batch_size=args.batch_size))
        print_summary(result.stats)
        print(f"wall time: {time.perf_counter() - started:.1f}s")
        failures = threshold_failures(args, result.stats)
        if failures:
            print("threshold failures:")
            for failure in failures:
                print(f"  {failure}")
        return 1 if failures else 0

    with ThreadPoolExecutor(max_workers=max(1, args.clients)) as executor:
        futures = [
            executor.submit(
                SmokeClient(base_url=args.base_url,
                            api_key=args.api_key,
                            timeout=args.timeout,
                            client_id=client_id).run,
                iterations=max(1, args.iterations),
                batch_size=max(1, args.batch_size),
                complete=bool(args.complete),
                update_existing=bool(args.update_existing),
                reuse_rows=bool(args.reuse_rows),
                source_key=str(args.source_key or ""),
                page_limit=max(1, int(args.page_limit or 100)),
            )
            for client_id in range(1, max(1, args.clients) + 1)
        ]
        for future in as_completed(futures):
            result.extend(future.result())

    print_summary(result.stats)
    print(f"wall time: {time.perf_counter() - started:.1f}s")
    failures = threshold_failures(args, result.stats)
    if failures:
        print("threshold failures:")
        for failure in failures:
            print(f"  {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
