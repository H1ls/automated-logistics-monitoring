from __future__ import annotations

from Navigation_Bot.core.repositories.postgres_task_repository import PostgresTaskRepository
from Navigation_Bot.core.storage.postgres_connection import connect_postgres


def main() -> int:
    with connect_postgres() as connection:
        repository = PostgresTaskRepository(connection)
        rows = repository.get()
    print(f"PostgreSQL active rows loaded: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
