import pytest
from types import SimpleNamespace

from LogistX.onec.scenarios.base import ScenarioError
from LogistX.onec.scenarios.close_race import CloseRaceScenario

class TestScenarioStage:

    def test_run_step_wraps_error_with_actual_stage(self):
        scenario = CloseRaceScenario.__new__(CloseRaceScenario)
        scenario.log = lambda *_: None
        step = SimpleNamespace(stage='fill_times', run=lambda _ctx: (_ for _ in ()).throw(RuntimeError('broken')))
        with pytest.raises(ScenarioError) as raised:
            scenario._run_step(step, object(), [])
        assert raised.value.stage == 'fill_times'
        assert raised.value.message == 'broken'

    def test_run_closes_card_after_incomplete_wialon_payload(self):
        scenario = CloseRaceScenario.__new__(CloseRaceScenario)
        scenario.log = lambda *_: None
        scenario.errors = SimpleNamespace(safe_abort=lambda *_: None)
        scenario.precheck_executor = None
        scenario._start_precheck = lambda _ctx: (None, None)
        scenario._elapsed = lambda: 0.0
        submitted = []
        scenario.session = SimpleNamespace(submit_ctrl_enter=lambda: submitted.append(True))
        calls = []

        def step(name, action=None):

            def run(ctx):
                calls.append(name)
                if action:
                    return action(ctx)
                return None
            return SimpleNamespace(stage=name, run=run)
        scenario.find_race_step = step('find_race')
        scenario.open_race_step = step('open_race')
        scenario.capture_ui_step = step('capture_race_ui')
        scenario.fill_departure_step = step('fill_departure')
        scenario.wialon_precheck_step = step('wialon_precheck', lambda _ctx: {'status': 'done'})
        scenario.fetch_wialon_times_step = step('fetch_wialon_times', lambda ctx: ctx.state.update({'wialon_has_complete_payload': False, 'wialon_payload': {'load_in': '', 'load_out': '', 'unload_in': '03.07.2026 15:38:13', 'unload_out': '03.07.2026 17:44:23'}}))
        scenario.fill_times_step = step('fill_times')
        scenario.driver_rating_step = step('driver_rating')
        scenario.submit_step = step('submit')
        ctx = SimpleNamespace(departure_dt='21.06.2026 09:00', load_in=None, load_out=None, unload_in=None, unload_out=None, state={})
        result = scenario.run(ctx)
        assert result.ok
        assert result.stage == 'fetch_wialon_times'
        assert submitted == [True]
        assert ctx.state['wialon_missing_keys'] == ['load_in', 'load_out']
        assert ctx.state['close_status'] == 'closed_without_complete_wialon_payload'
        assert 'fill_times' not in calls
        assert 'driver_rating' not in calls
        assert 'submit' not in calls
