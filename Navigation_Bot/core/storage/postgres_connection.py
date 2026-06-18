from __future__ import annotations

from pathlib import Path
from typing import Any

from Navigation_Bot.core.database_config import DatabaseConfig

POSTGRES_SCHEMA_FILE = Path(__file__).with_name("postgres_schema.sql")


def _import_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PostgreSQL driver is not installed. Run: python -m pip install \"psycopg[binary]==3.3.2\"") from exc
    return psycopg, dict_row


def connect_postgres(dsn: str | None = None):
    psycopg, dict_row = _import_psycopg()
    config = DatabaseConfig.from_env()
    return psycopg.connect(dsn or config.postgres_dsn, row_factory=dict_row, autocommit=True)


def initialize_postgres_schema(dsn: str | None = None) -> None:
    sql = POSTGRES_SCHEMA_FILE.read_text(encoding="utf-8")
    with connect_postgres(dsn) as connection:
        connection.execute(sql)


def postgres_healthcheck(dsn: str | None = None, connection: Any | None = None) -> dict[str, Any]:
    if connection is not None:
        return _postgres_healthcheck(connection)

    with connect_postgres(dsn) as direct_connection:
        return _postgres_healthcheck(direct_connection)


def _postgres_healthcheck(connection: Any) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            current_user AS current_user,
            current_database() AS current_database,
            version() AS version
        """
    ).fetchone()
    table_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM information_schema.tables
        WHERE table_schema = 'public'
        """
    ).fetchone()
    return {"current_user": row["current_user"],
            "current_database": row["current_database"],
            "version": row["version"],
            "public_table_count": table_count["count"]}
