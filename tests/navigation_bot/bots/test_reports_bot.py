import pytest
import sys
from types import SimpleNamespace
_selenium_exceptions = SimpleNamespace(ElementClickInterceptedException=Exception, NoSuchElementException=Exception, StaleElementReferenceException=Exception, TimeoutException=TimeoutError)
_by = SimpleNamespace(By=SimpleNamespace(CSS_SELECTOR='css', XPATH='xpath'))
_keys = SimpleNamespace(Keys=SimpleNamespace(CONTROL='ctrl', ENTER='enter', TAB='tab', ESCAPE='escape', DOWN='down'))
_actions = SimpleNamespace(ActionChains=lambda *_args, **_kwargs: None)
_wait = SimpleNamespace(WebDriverWait=lambda *_args, **_kwargs: None)
_ec = SimpleNamespace(expected_conditions=SimpleNamespace())
sys.modules.setdefault('selenium', SimpleNamespace())
sys.modules.setdefault('selenium.common', SimpleNamespace(exceptions=_selenium_exceptions))
sys.modules.setdefault('selenium.common.exceptions', _selenium_exceptions)
sys.modules.setdefault('selenium.webdriver', SimpleNamespace(common=SimpleNamespace(by=_by, keys=_keys), ActionChains=None))
sys.modules.setdefault('selenium.webdriver.common', SimpleNamespace(by=_by, keys=_keys, action_chains=_actions))
sys.modules.setdefault('selenium.webdriver.common.by', _by)
sys.modules.setdefault('selenium.webdriver.common.keys', _keys)
sys.modules.setdefault('selenium.webdriver.common.action_chains', _actions)
sys.modules.setdefault('selenium.webdriver.support', SimpleNamespace(expected_conditions=_ec.expected_conditions, ui=_wait))
sys.modules.setdefault('selenium.webdriver.support.expected_conditions', _ec.expected_conditions)
sys.modules.setdefault('selenium.webdriver.support.ui', _wait)
from Navigation_Bot.bots.scenarios.reports_bot import WialonReportsBot

class _Element:

    def __init__(self, text='', children=None):
        self.text = text
        self._children = children or []

    def find_elements(self, *_args, **_kwargs):
        return self._children

def _row(number, zone, time_in, time_out):
    return _Element(children=[_Element(number), _Element('SANY U322AO 250'), _Element(zone), _Element(time_in), _Element(time_out)])

def _detail_row(unit, zone, time_in, time_out, address=''):
    return _Element(children=[_Element(unit), _Element(zone), _Element(time_in), _Element(time_out), _Element(address)])

class TestWialonReportsBotExtractTimes:

    @staticmethod
    def _make_bot(rows, messages=None):
        table = _Element(children=rows)
        bot = WialonReportsBot.__new__(WialonReportsBot)
        bot.selectors = {'results_table_css': 'table', 'result_rows_css': 'tr', 'row_cells_css': 'td'}
        bot.log = messages.append if messages is not None else lambda *_args, **_kwargs: None
        bot._wait_present_css = lambda *_args, **_kwargs: table
        return bot

    def test_merges_same_zone_when_overlapping_zone_row_is_between_parts(self):
        rows = [_row('1.4', 'Kazan_Magistralnaya_77', '13.06.2026 01:00:26', '13.06.2026 11:28:47'), _row('1.5', 'Tikhoretskaya', '13.06.2026 03:56:52', '13.06.2026 04:09:37'), _row('1.6', 'Kazan_Magistralnaya_77', '13.06.2026 11:28:52', '13.06.2026 16:22:12'), _row('1.7', 'Unload', '13.06.2026 18:00:00', '13.06.2026 18:30:00')]
        bot = self._make_bot(rows)
        result = bot.extract_times('Kazan_Magistralnaya_77', 'Unload')
        assert result['load_in'] == '13.06.2026 01:00:26'
        assert result['load_out'] == '13.06.2026 16:22:12'
        assert result['unload_in'] == '13.06.2026 18:00:00'
        assert result['unload_out'] == '13.06.2026 18:30:00'

    def test_extracts_unload_even_when_load_zone_is_absent_from_report_details(self):
        rows = [_detail_row('SITRAK М289ТМ 790', 'О.НСК.Обь', '03.07.2026 11:09:30', '03.07.2026 11:45:40'), _detail_row('SITRAK М289ТМ 790', 'О.НСК.Садовый', '03.07.2026 15:38:13', '03.07.2026 17:44:23')]
        bot = self._make_bot(rows)
        result = bot.extract_times('О.УФА_РФЦ', 'О.НСК.Садовый')
        assert result['load_in'] == ''
        assert result['load_out'] == ''
        assert result['unload_in'] == '03.07.2026 15:38:13'
        assert result['unload_out'] == '03.07.2026 17:44:23'

    def test_warns_when_unload_zone_has_later_unmerged_interval(self):
        rows = [_row('1.1', 'O.NSK.Ob', '15.06.2026 12:57:41', '15.06.2026 20:37:59'), _row('1.2', 'O.KHBR.Rakitnoe', '20.06.2026 08:33:53', '20.06.2026 09:17:59'), _row('1.3', 'O.KHBR.Rakitnoe', '20.06.2026 09:18:54', '20.06.2026 10:45:11'), _row('1.4', 'O.KHBR.Rakitnoe', '20.06.2026 10:47:17', '20.06.2026 13:06:31'), _row('1.5', 'O.KHBR.Rakitnoe', '20.06.2026 13:26:54', '20.06.2026 18:04:14')]
        messages = []
        bot = self._make_bot(rows, messages)
        result = bot.extract_times('O.NSK.Ob', 'O.KHBR.Rakitnoe')
        assert result['unload_out'] == '20.06.2026 13:06:31'
        assert any(('Есть дополнительное время' in message and '20.06.2026 13:26:54' in message and ('20.06.2026 18:04:14' in message) and ('Проверить вручную' in message) for message in messages))

    def test_wialon_stage_error_contains_operation_and_exception_type(self):
        bot = WialonReportsBot.__new__(WialonReportsBot)

        def fail():
            raise TimeoutError()
        with pytest.raises(RuntimeError, match='Wialon: ошибка на этапе «выбор машины»: TimeoutError'):
            bot._run_wialon_stage('выбор машины', fail)

    def test_run_and_wait_identifies_spinner_timeout(self):
        bot = WialonReportsBot.__new__(WialonReportsBot)
        bot.selectors = {'run_button_xpath': 'run', 'spinner_waiting_css': 'spinner', 'results_table_css': 'table'}
        bot._safe_click_xpath = lambda *_args, **_kwargs: None
        bot._wait_present_css = lambda *_args, **_kwargs: object()
        bot._wait_gone_css = lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError())
        with pytest.raises(RuntimeError, match='не дождались исчезновения spinner_waiting за 75 с'):
            bot.run_and_wait(timeout=75)
