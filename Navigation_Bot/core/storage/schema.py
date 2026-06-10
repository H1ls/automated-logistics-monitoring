from __future__ import annotations

import sqlite3

"""
SQLite-схема проекта.

Здесь описаны таблицы, индексы и простые миграции, которые выполняются приоткрытии БД через open_database(). 
Схема уже нормализована: рейс хранится в tasks, справочники вынесены в carriers/vehicles/drivers, точки маршрута -
в route_points, а история и заметки - в отдельных таблицах.
"""

SCHEMA_VERSION = 4

# Таблицы создаются через IF NOT EXISTS, поэтому этот блок безопасно выполнять
# при каждом запуске приложения. Изменения существующих таблиц делаются ниже
# отдельными миграциями.
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS carriers (
    -- Перевозчики / КА. Используются и для рейсов, и для водителей.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS vehicles (
    -- Транспортные средства. plate_number и monitoring_id уникальны.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL,
    monitoring_id INTEGER,
    monitoring_name TEXT NOT NULL DEFAULT '',
    monitoring_center TEXT NOT NULL DEFAULT '',
    vehicle_full_name TEXT NOT NULL DEFAULT '',
    carrier_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    brand TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    UNIQUE (plate_number),
    UNIQUE (monitoring_id)
);

CREATE TABLE IF NOT EXISTS drivers (
    -- Водители. carrier_id показывает, к какому перевозчику водитель относится.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    carrier_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    -- Центральная таблица рейсов.
    -- trip_number - внутренний номер рейса в нашей БД.
    -- google_sheet_row - номер строки Google, куда можно писать данные обратно.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_number INTEGER NOT NULL,
    google_sheet_id TEXT,
    google_worksheet_id TEXT,
    google_worksheet_title TEXT,
    google_sheet_row INTEGER,
    vehicle_id INTEGER,
    driver_id INTEGER,
    carrier_id INTEGER,
    status TEXT NOT NULL DEFAULT 'new',
    planned_start_at TEXT,
    planned_end_at TEXT,
    actual_start_at TEXT,
    actual_end_at TEXT,
    completed_at TEXT,
    completion_source TEXT,
    raw_load TEXT NOT NULL DEFAULT '',
    raw_unload TEXT NOT NULL DEFAULT '',
    comm_load TEXT NOT NULL DEFAULT '',
    comm_unload TEXT NOT NULL DEFAULT '',
    highlight_until TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON UPDATE CASCADE ON DELETE SET NULL,
    FOREIGN KEY (driver_id) REFERENCES drivers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    FOREIGN KEY (carrier_id) REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    UNIQUE (trip_number)
);

CREATE TABLE IF NOT EXISTS route_points (
    -- Точки маршрута: погрузки и выгрузки.
    -- Уникальность (task_id, point_type, sequence) позволяет обновлять точку
    -- без создания нового id при изменении адреса/времени.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    point_type TEXT NOT NULL CHECK (point_type IN ('load', 'unload')),
    location TEXT NOT NULL DEFAULT '',
    latitude REAL,
    longitude REAL,
    geo_accuracy_m REAL,
    geocoded_at TEXT,
    geocoding_source TEXT,
    scheduled_time TEXT,
    actual_arrival_at TEXT,
    actual_departure_at TEXT,
    comment TEXT NOT NULL DEFAULT '',
    is_processed INTEGER NOT NULL DEFAULT 0 CHECK (is_processed IN (0, 1)),
    processed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    UNIQUE (task_id, point_type, sequence)
);

CREATE TABLE IF NOT EXISTS status_events (
    -- История важных изменений: статус рейса, изменения route_points, отметки.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    route_point_id INTEGER,
    event_type TEXT NOT NULL,
    field_name TEXT NOT NULL DEFAULT '',
    old_value TEXT,
    new_value TEXT,
    message TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (route_point_id) REFERENCES route_points(id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS task_notes (
    -- Заметки пользователя по рейсу, включая вложения.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT 'user',
    media_type TEXT,
    media_path TEXT,
    is_important INTEGER NOT NULL DEFAULT 0 CHECK (is_important IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS route_estimates (
    -- История расчетов маршрута/ETA.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    target_route_point_id INTEGER,
    target_sequence INTEGER NOT NULL DEFAULT 0,
    distance_km REAL NOT NULL DEFAULT 0,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    arrival_time TEXT NOT NULL DEFAULT '',
    on_time INTEGER NOT NULL DEFAULT 0 CHECK (on_time IN (0, 1)),
    buffer_minutes INTEGER NOT NULL DEFAULT 0,
    time_buffer_text TEXT NOT NULL DEFAULT '',
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (target_route_point_id) REFERENCES route_points(id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS vehicle_navigation_history (
    -- История навигации ТС. Может быть привязана к рейсу через task_id.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL,
    task_id INTEGER,
    latitude REAL,
    longitude REAL,
    coordinates TEXT NOT NULL DEFAULT '',
    geo_text TEXT NOT NULL DEFAULT '',
    geo_zona TEXT NOT NULL DEFAULT '',
    speed_kmh REAL,
    gps_fix_text TEXT NOT NULL DEFAULT '',
    gps_fix_age_seconds INTEGER,
    has_fresh_coordinates INTEGER NOT NULL DEFAULT 0 CHECK (has_fresh_coordinates IN (0, 1)),
    is_navigation_stale INTEGER NOT NULL DEFAULT 0 CHECK (is_navigation_stale IN (0, 1)),
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE SET NULL
);
"""

# Индексы ускоряют основные сценарии: загрузка активных рейсов, история по рейсу,
# история навигации по ТС/рейсу.
CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_vehicles_carrier_id
    ON vehicles(carrier_id);

CREATE INDEX IF NOT EXISTS idx_vehicles_monitoring_name
    ON vehicles(monitoring_name);

CREATE INDEX IF NOT EXISTS idx_drivers_carrier_id
    ON drivers(carrier_id);

CREATE INDEX IF NOT EXISTS idx_tasks_vehicle_status
    ON tasks(vehicle_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_planned_start_at
    ON tasks(planned_start_at);

CREATE INDEX IF NOT EXISTS idx_tasks_google_source
    ON tasks(google_sheet_id, google_worksheet_id, google_sheet_row);

CREATE INDEX IF NOT EXISTS idx_route_points_task_sequence
    ON route_points(task_id, sequence);

CREATE INDEX IF NOT EXISTS idx_route_points_task_type
    ON route_points(task_id, point_type);

CREATE INDEX IF NOT EXISTS idx_status_events_task_created
    ON status_events(task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_task_notes_task_created
    ON task_notes(task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_route_estimates_task_calculated
    ON route_estimates(task_id, calculated_at);

CREATE INDEX IF NOT EXISTS idx_vehicle_navigation_vehicle_collected
    ON vehicle_navigation_history(vehicle_id, collected_at);

CREATE INDEX IF NOT EXISTS idx_vehicle_navigation_task_collected
    ON vehicle_navigation_history(task_id, collected_at);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Создает таблицы/индексы и применяет простые миграции схемы."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(CREATE_TABLES_SQL)
    _migrate_tasks_trip_number(connection)
    _ensure_column(connection, "vehicles", "monitoring_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "vehicles", "monitoring_center", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "vehicles", "vehicle_full_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "tasks", "completed_at", "TEXT")
    _ensure_column(connection, "tasks", "completion_source", "TEXT")
    connection.executescript(CREATE_INDEXES_SQL)
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    connection.commit()


def _migrate_tasks_trip_number(connection: sqlite3.Connection) -> None:
    """Переименовывает старую колонку task_index в trip_number без потери данных."""
    columns = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if "trip_number" in columns or "task_index" not in columns:
        return

    connection.execute("ALTER TABLE tasks RENAME COLUMN task_index TO trip_number")


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column in columns:
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
