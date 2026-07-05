from Navigation_Bot.gui.widgets.table.table_display_formatter import TableDisplayFormatter

class TestTableDisplayFormatter:

    def test_single_unload_with_comment_has_no_status_suffix(self):
        formatter = TableDisplayFormatter()
        text = formatter.unload_points_text_with_status({'unloads': [{'date': '03.07.2026', 'time': '08:00', 'address': 'Приморский край, г.Владивосток Карьерная 20А'}, {'comment': '89084474105'}], 'processed_unloads': [False]})
        assert '⬜️' not in text
        assert '☑️' not in text

    def test_multiple_unloads_show_status_suffixes_only_on_address_points(self):
        formatter = TableDisplayFormatter()
        text = formatter.unload_points_text_with_status({'unloads': [{'date': '03.07.2026', 'time': '08:00', 'address': 'A'}, {'date': '04.07.2026', 'time': '09:00', 'address': 'B'}, {'comment': 'phone'}], 'processed_unloads': [True, False]})
        assert 'A  ☑️' in text
        assert 'B  ⬜️' in text
        assert 'phone  ⬜️' not in text
