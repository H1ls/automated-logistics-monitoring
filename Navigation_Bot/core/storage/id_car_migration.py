from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from Navigation_Bot.core.paths import CONFIG_DIR

ID_CAR_JSON_FILEPATH = CONFIG_DIR / "Id_car.json"


def load_id_car_entries(path: Path = ID_CAR_JSON_FILEPATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    if isinstance(raw, dict):
        return [raw]
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def migrate_id_car_json(vehicle_repository: Any, *,
                        path: Path = ID_CAR_JSON_FILEPATH,
                        log: Callable[[str], None] | None = None) -> int:
    entries = load_id_car_entries(path)
    if not entries:
        if log:
            log(f"Id_car migration skipped: {path} not found or empty")
        return 0

    vehicle_repository.save_registry_entries(entries)
    if log:
        log(f"Id_car migration: vehicles imported/updated: {len(entries)}")
    return len(entries)


def main() -> int:
    from Navigation_Bot.core.database_config import DatabaseConfig
    from Navigation_Bot.core.repositories.postgres_vehicle_repository import PostgresVehicleRepository
    from Navigation_Bot.core.storage.postgres_connection import connect_postgres, initialize_postgres_schema

    config = DatabaseConfig.from_env()
    if not config.is_postgres:
        raise RuntimeError("Id_car migration now requires DB_BACKEND=postgres")

    initialize_postgres_schema(config.postgres_dsn)
    with connect_postgres(config.postgres_dsn) as connection:
        count = migrate_id_car_json(PostgresVehicleRepository(connection))
        connection.commit()

    print(f"Id_car migration complete: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
