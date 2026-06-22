from unittest import TestCase

from Navigation_Bot.bots.scenarios.reports_bot import WialonReportsBot


class _Element:
    def __init__(self, text="", children=None):
        self.text = text
        self._children = children or []

    def find_elements(self, *_args, **_kwargs):
        return self._children


def _row(number, zone, time_in, time_out):
    return _Element(children=[
        _Element(number),
        _Element("SANY U322AO 250"),
        _Element(zone),
        _Element(time_in),
        _Element(time_out),
    ])


class WialonReportsBotExtractTimesTests(TestCase):
    @staticmethod
    def _make_bot(rows, messages=None):
        table = _Element(children=rows)
        bot = WialonReportsBot.__new__(WialonReportsBot)
        bot.selectors = {
            "results_table_css": "table",
            "result_rows_css": "tr",
            "row_cells_css": "td",
        }
        bot.log = (messages.append if messages is not None else lambda *_args, **_kwargs: None)
        bot._wait_present_css = lambda *_args, **_kwargs: table
        return bot

    def test_merges_same_zone_when_overlapping_zone_row_is_between_parts(self):
        rows = [
            _row("1.4", "Kazan_Magistralnaya_77", "13.06.2026 01:00:26", "13.06.2026 11:28:47"),
            _row("1.5", "Tikhoretskaya", "13.06.2026 03:56:52", "13.06.2026 04:09:37"),
            _row("1.6", "Kazan_Magistralnaya_77", "13.06.2026 11:28:52", "13.06.2026 16:22:12"),
            _row("1.7", "Unload", "13.06.2026 18:00:00", "13.06.2026 18:30:00"),
        ]
        bot = self._make_bot(rows)

        result = bot.extract_times("Kazan_Magistralnaya_77", "Unload")

        self.assertEqual(result["load_in"], "13.06.2026 01:00:26")
        self.assertEqual(result["load_out"], "13.06.2026 16:22:12")
        self.assertEqual(result["unload_in"], "13.06.2026 18:00:00")
        self.assertEqual(result["unload_out"], "13.06.2026 18:30:00")

    def test_warns_when_unload_zone_has_later_unmerged_interval(self):
        rows = [
            _row("1.1", "O.NSK.Ob", "15.06.2026 12:57:41", "15.06.2026 20:37:59"),
            _row("1.2", "O.KHBR.Rakitnoe", "20.06.2026 08:33:53", "20.06.2026 09:17:59"),
            _row("1.3", "O.KHBR.Rakitnoe", "20.06.2026 09:18:54", "20.06.2026 10:45:11"),
            _row("1.4", "O.KHBR.Rakitnoe", "20.06.2026 10:47:17", "20.06.2026 13:06:31"),
            _row("1.5", "O.KHBR.Rakitnoe", "20.06.2026 13:26:54", "20.06.2026 18:04:14"),
        ]
        messages = []
        bot = self._make_bot(rows, messages)

        result = bot.extract_times("O.NSK.Ob", "O.KHBR.Rakitnoe")

        self.assertEqual(result["unload_out"], "20.06.2026 13:06:31")
        self.assertTrue(any(
            "Есть дополнительное время" in message
            and "20.06.2026 13:26:54" in message
            and "20.06.2026 18:04:14" in message
            and "Проверить вручную" in message
            for message in messages
        ))

    def test_wialon_stage_error_contains_operation_and_exception_type(self):
        bot = WialonReportsBot.__new__(WialonReportsBot)

        def fail():
            raise TimeoutError()

        with self.assertRaisesRegex(
            RuntimeError,
            "Wialon: ошибка на этапе «выбор машины»: TimeoutError",
        ):
            bot._run_wialon_stage("выбор машины", fail)

    def test_run_and_wait_identifies_spinner_timeout(self):
        bot = WialonReportsBot.__new__(WialonReportsBot)
        bot.selectors = {
            "run_button_xpath": "run",
            "spinner_waiting_css": "spinner",
            "results_table_css": "table",
        }
        bot._safe_click_xpath = lambda *_args, **_kwargs: None
        bot._wait_present_css = lambda *_args, **_kwargs: object()
        bot._wait_gone_css = lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError())

        with self.assertRaisesRegex(
            RuntimeError,
            "не дождались исчезновения spinner_waiting за 75 с",
        ):
            bot.run_and_wait(timeout=75)
