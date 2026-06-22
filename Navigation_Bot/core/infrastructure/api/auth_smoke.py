from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(slots=True)
class Check:
    role: str
    name: str
    method: str
    path: str
    expected_status: int
    json: dict[str, Any] | None = None


@dataclass(slots=True)
class CheckResult:
    check: Check
    actual_status: int | None
    elapsed_ms: float
    ok: bool
    error: str = ""


def role_checks(role: str) -> list[Check]:
    common = [
        Check(role, "read me", "GET", "/api/v1/me", 200),
        Check(role, "read health", "GET", "/api/v1/health", 200),
        Check(role, "read tasks", "GET", "/api/v1/tasks?source_key=auth_smoke&strict_source_key=true&limit=1", 200),
    ]

    if role == "viewer":
        return common + [
            Check(role, "deny complete", "POST", "/api/v1/tasks/complete/batch", 403,
                  {"row_identities": [999999998], "source": "auth_smoke"}),
            Check(role, "deny users", "GET", "/api/v1/users", 403),
            Check(role, "deny audit", "GET", "/api/v1/audit-log", 403),
        ]

    if role == "dispatcher":
        return common + [
            Check(role, "allow complete", "POST", "/api/v1/tasks/complete/batch", 200,
                  {"row_identities": [999999998], "source": "auth_smoke"}),
            Check(role, "deny users", "GET", "/api/v1/users", 403),
            Check(role, "deny audit", "GET", "/api/v1/audit-log", 403),
        ]

    if role == "admin":
        return common + [
            Check(role, "allow complete", "POST", "/api/v1/tasks/complete/batch", 200,
                  {"row_identities": [999999998], "source": "auth_smoke"}),
            Check(role, "allow users", "GET", "/api/v1/users", 200),
            Check(role, "allow audit", "GET", "/api/v1/audit-log?limit=1", 200),
        ]

    return []


def run_check(base_url: str, api_key: str, check: Check, timeout: float) -> CheckResult:
    started = time.perf_counter()
    status_code = None
    try:
        response = requests.request(check.method,
                                    f"{base_url.rstrip('/')}{check.path}",
                                    headers={"X-API-Key": api_key},
                                    json=check.json,
                                    timeout=timeout)
        status_code = response.status_code
        elapsed_ms = (time.perf_counter() - started) * 1000
        ok = status_code == check.expected_status
        error = "" if ok else response.text[:300]
        return CheckResult(check, status_code, elapsed_ms, ok, error)
    except Exception as exc:
        return CheckResult(check,
                           status_code,
                           (time.perf_counter() - started) * 1000,
                           False,
                           str(exc))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Role/access smoke test for Navigation Bot API.")
    parser.add_argument("--base-url", default=os.getenv("NAV_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-key", default=os.getenv("NAV_ADMIN_API_KEY") or os.getenv("NAV_API_KEY", ""))
    parser.add_argument("--dispatcher-key", default=os.getenv("NAV_DISPATCHER_API_KEY", ""))
    parser.add_argument("--viewer-key", default=os.getenv("NAV_VIEWER_API_KEY", ""))
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    role_keys = {
        "admin": args.admin_key,
        "dispatcher": args.dispatcher_key,
        "viewer": args.viewer_key,
    }

    missing = [role for role, key in role_keys.items() if not key]
    if missing:
        print(f"missing keys for roles: {', '.join(missing)}")
        print("set NAV_ADMIN_API_KEY, NAV_DISPATCHER_API_KEY, NAV_VIEWER_API_KEY or pass --*-key")
        return 2

    results: list[CheckResult] = []
    for role, api_key in role_keys.items():
        for check in role_checks(role):
            results.append(run_check(args.base_url, api_key, check, args.timeout))

    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(
            f"{status} {result.check.role:10s} {result.check.name:15s} "
            f"{result.check.method:4s} {result.check.path:55s} "
            f"expected={result.check.expected_status} actual={result.actual_status} "
            f"{result.elapsed_ms:.0f}ms"
        )
        if result.error:
            print(f"  {result.error}")

    failures = [result for result in results if not result.ok]
    print(f"checks: {len(results)}, failures: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
