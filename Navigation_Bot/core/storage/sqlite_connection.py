from __future__ import annotations

import sqlite3
from pathlib import Path

from Navigation_Bot.core.storage.schema import initialize_schema


def connect_sqlite(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def open_database(db_path: str | Path) -> sqlite3.Connection:
    connection = connect_sqlite(db_path)
    initialize_schema(connection)
    return connection
