from Navigation_Bot.core.repositories.postgres_task_lookup import PostgresTaskLookup


class FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        if "google_worksheet_title IS NULL" in query:
            return FakeCursor({"trip_number": 42})
        if "COALESCE(MAX(trip_number)" in query:
            return FakeCursor({"value": 99})
        return FakeCursor(None)


def test_resolve_trip_number_with_source_key_matches_legacy_null_source_row():
    connection = FakeConnection()
    lookup = PostgresTaskLookup(connection, source_key="Sheet A")

    result = lookup.resolve_trip_number({"google_sheet_row": 7}, 7)

    assert result == 42
    assert connection.calls[0][1] == (7, "Sheet A", "Sheet A")
