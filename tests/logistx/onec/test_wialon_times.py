import pytest
from datetime import datetime
from types import SimpleNamespace
from LogistX.onec.steps.fetch_wialon_times import FetchWialonTimesStep
from LogistX.onec.wialon_times import WialonMeta, WialonTimesPolicy, WialonTimesService

class TestWialonMeta:

    def test_reads_and_validates_context_metadata(self):
        ctx = SimpleNamespace(meta={'unit': ' Truck ', 'load_zone': ' Load ', 'unload_zone': ' Unload '})
        meta = WialonMeta.from_context(ctx)
        assert meta == WialonMeta('Truck', 'Load', 'Unload')

    def test_precheck_does_not_require_load_zone(self):
        ctx = SimpleNamespace(meta={'unit': 'Truck', 'unload_zone': 'Unload'})
        meta = WialonMeta.from_context(ctx, require_load_zone=False)
        assert meta.load_zone == ''

class TestWialonTimesPolicy:

    def test_guard_clears_recent_unload_without_mutating_source(self):
        source = {'unload_in': '21.06.2026 12:00:00', 'unload_out': '21.06.2026 12:50:00'}
        policy = WialonTimesPolicy(unload_out_guard_minutes=20, now_func=lambda: datetime(2026, 6, 21, 13, 0, 0), log_func=lambda *_: None)
        result = policy.apply(source)
        assert result['unload_out'] == ''
        assert source['unload_out'] == '21.06.2026 12:50:00'

    def test_rejects_invalid_time_and_reversed_interval(self):
        policy = WialonTimesPolicy()
        with pytest.raises(RuntimeError, match='некорректное время'):
            policy.apply({'load_in': 'invalid'})
        with pytest.raises(RuntimeError, match='load_out раньше load_in'):
            policy.apply({'load_in': '21.06.2026 13:00:00', 'load_out': '21.06.2026 12:00:00'})

    def test_rejects_out_without_in(self):
        with pytest.raises(RuntimeError, match='unload_out .* unload_in'):
            WialonTimesPolicy().apply({'unload_out': '21.06.2026 12:00:00'})

    def test_future_unload_out_is_cleared_without_mutating_source(self):
        source = {'unload_in': '21.06.2026 12:00:00', 'unload_out': '21.06.2026 14:00:00'}
        policy = WialonTimesPolicy(now_func=lambda: datetime(2026, 6, 21, 13, 0, 0), log_func=lambda *_: None)
        result = policy.apply(source)
        assert result['unload_out'] == ''
        assert source['unload_out'] == '21.06.2026 14:00:00'

class _ReportsBot:

    def __init__(self):
        self.kwargs = None

    def run_geo_report_for_trip(self, **kwargs):
        self.kwargs = kwargs
        return {'load_in': 'value'}

class TestWialonTimesService:

    def test_service_only_forwards_explicit_report_parameters(self):
        reportsbot = _ReportsBot()
        service = WialonTimesService(reportsbot, log_func=lambda *_: None)
        meta = WialonMeta('Truck', 'Load', 'Unload')
        result = service.fetch_trip(meta, 'from', 'to')
        assert result == {'load_in': 'value'}
        assert reportsbot.kwargs['unit'] == 'Truck'
        assert reportsbot.kwargs['load_zone'] == 'Load'
        assert reportsbot.kwargs['unload_zone'] == 'Unload'

class _Service:

    def fetch_trip(self, meta, date_from, date_to):
        self.meta = meta
        self.interval = (date_from, date_to)
        return {'raw': True}

class _Policy:

    def apply(self, payload):
        self.payload = payload
        return {'load_in': '21.06.2026 10:00:00', 'load_out': '21.06.2026 11:00:00', 'unload_in': '21.06.2026 12:00:00', 'unload_out': '21.06.2026 13:00:00'}

class TestFetchWialonTimesStep:

    def test_step_transfers_policy_result_to_context(self):
        service = _Service()
        policy = _Policy()
        step = FetchWialonTimesStep(log_func=lambda *_: None, service=service, policy=policy)
        ctx = SimpleNamespace(departure_dt='21.06.2026 09:00', meta={'unit': 'Truck', 'load_zone': 'Load', 'unload_zone': 'Unload'}, state={}, load_in=None, load_out=None, unload_in=None, unload_out=None)
        step.run(ctx)
        assert policy.payload == {'raw': True}
        assert ctx.load_in == '21.06.2026 10:00:00'
        assert ctx.unload_out == '21.06.2026 13:00:00'
        assert ctx.state['wialon_payload']['load_out'] == '21.06.2026 11:00:00'
        assert ctx.state['wialon_has_complete_payload']

    def test_step_marks_partial_payload_as_incomplete(self):
        ctx = SimpleNamespace(state={}, load_in=None, load_out=None, unload_in=None, unload_out=None)
        FetchWialonTimesStep._apply_to_context(ctx, {'load_in': '', 'load_out': '', 'unload_in': '03.07.2026 15:38:13', 'unload_out': '03.07.2026 17:44:23'})
        assert ctx.state['wialon_has_times']
        assert not ctx.state['wialon_has_complete_payload']
