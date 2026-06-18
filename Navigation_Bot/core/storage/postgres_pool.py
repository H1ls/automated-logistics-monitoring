from __future__ import annotations

import os
from typing import Any

from Navigation_Bot.core.database_config import DatabaseConfig


def _import_pool():
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PostgreSQL connection pool is not installed. Run: python -m pip install psycopg_pool==3.3.0") from exc
    return ConnectionPool, dict_row


def create_postgres_pool(dsn: str | None = None) -> Any:
    ConnectionPool, dict_row = _import_pool()
    config = DatabaseConfig.from_env()
    min_size = _env_int("POSTGRES_POOL_MIN_SIZE", 2)
    max_size = _env_int("POSTGRES_POOL_MAX_SIZE", 10)
    timeout = float(os.getenv("POSTGRES_POOL_TIMEOUT", "10") or "10")
    return ConnectionPool(conninfo=dsn or config.postgres_dsn,
                          min_size=min_size,
                          max_size=max(min_size, max_size),
                          timeout=timeout,
                          kwargs={"autocommit": True,
                                  "row_factory": dict_row, },
                          open=False)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default
