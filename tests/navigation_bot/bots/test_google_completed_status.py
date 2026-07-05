from Navigation_Bot.bots.google_sheets_manager import GoogleSheetsManager
from Navigation_Bot.core.application.services.tasks_service import TasksService
from Navigation_Bot.core.application.services.google.google_sync_service import GoogleSyncService

def test_google_status_completed_variants_are_skipped():
    completed_values = ['Готов', 'Готово', '= Готово', '=Готово', '  =  готово  ']
    for value in completed_values:
        assert GoogleSheetsManager._is_completed_status(value)

def test_google_status_active_variants_are_not_skipped():
    active_values = ['', 'В работе', 'Готовится']
    for value in active_values:
        assert not GoogleSheetsManager._is_completed_status(value)

def test_fetch_current_sheet_rows_accepts_empty_active_result():

    class FakeSheets:

        def load_data(self):
            return {}
    service = GoogleSyncService(gsheet=FakeSheets(), google_writer=None, tasks_service=None, task_repository=None, vehicle_repository=None)
    ok, rows, err = service._fetch_current_sheet_rows()
    assert ok is True
    assert rows == {}
    assert err is None

def test_remove_completed_tasks_completes_missing_google_rows():

    class FakeRepository:

        def __init__(self):
            self.data = [{'google_sheet_row': 5, 'trip_number': 1005, 'status': 'active'}, {'google_sheet_row': 6, 'trip_number': 1006, 'status': 'active'}, {'trip_number': 2000, 'status': 'active'}]
            self.completed = []

        def get(self):
            return self.data

        def complete_row(self, real_idx, *, source='user'):
            row = self.data.pop(real_idx)
            row['status'] = 'completed'
            self.completed.append((row['google_sheet_row'], source))
            return (True, row, None)
    repository = FakeRepository()
    service = TasksService(task_repository=repository)
    ok, stats, err = service.remove_completed_tasks({6})
    assert ok is True
    assert err is None
    assert stats == {'deleted': 1}
    assert repository.completed == [(5, 'google')]
    assert [row.get('google_sheet_row') for row in repository.data] == [6, None]
