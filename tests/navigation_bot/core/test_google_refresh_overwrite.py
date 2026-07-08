from Navigation_Bot.core.application.services.tasks_service import TasksService


class FakeRepository:
    def __init__(self, data):
        self.data = data
        self.saved_sources = []

    def get(self):
        return self.data

    def save(self, *, source="user"):
        self.saved_sources.append(source)


def test_google_patch_rebuilds_route_points_from_fresh_google_text():
    repository = FakeRepository([
        {
            "index": 3051,
            "google_sheet_row": 3051,
            "trip_number": 9001,
            "ТС": "А123ВС 777",
            "Телефон": "79990000000",
            "ФИО": "Old Driver",
            "КА": "Old Carrier",
            "raw_load": "Россия, г. Москва 01.01.2026 10:00",
            "raw_unload": "Россия, г. Тула 02.01.2026 11:00",
            "loads": [{"sequence": 1, "address": "old load", "date": "", "time": ""}],
            "unloads": [{"sequence": 1, "address": "old unload", "date": "", "time": ""}],
            "processed": [True],
            "processed_unloads": [True],
        }
    ])
    service = TasksService(task_repository=repository)

    ok, row, err = service.apply_patch(
        0,
        {
            "index": 3051,
            "google_sheet_row": 3051,
            "raw_load": "Россия, г. Казань 03.01.2026 12:00",
            "raw_unload": "Россия, г. Самара 04.01.2026 13:00",
            "Погрузка": "Россия, г. Казань 03.01.2026 12:00",
            "Выгрузка": "Россия, г. Самара 04.01.2026 13:00",
        },
        source="google",
    )

    assert ok is True
    assert err is None
    assert row["trip_number"] == 9001
    assert row["google_sheet_row"] == 3051
    assert row["raw_unload"] == "Россия, г. Самара 04.01.2026 13:00"
    assert row["unloads"][0]["address"] != "old unload"
    assert "Самара" in row["unloads"][0]["address"]
    assert row["processed_unloads"] == [False]
    assert repository.saved_sources == ["google"]
