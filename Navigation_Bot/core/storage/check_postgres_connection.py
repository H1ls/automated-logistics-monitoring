from __future__ import annotations

from Navigation_Bot.core.storage.postgres_connection import postgres_healthcheck


def main() -> int:
    info = postgres_healthcheck()
    print(f"PostgreSQL OK: {info['current_user']}@{info['current_database']}")
    print(f"Public tables: {info['public_table_count']}")
    print(info["version"].splitlines()[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
