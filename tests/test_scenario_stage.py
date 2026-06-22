from types import SimpleNamespace
from unittest import TestCase

from LogistX.onec.scenarios.base import ScenarioError
from LogistX.onec.scenarios.close_race import CloseRaceScenario


class ScenarioStageTests(TestCase):
    def test_run_step_wraps_error_with_actual_stage(self):
        scenario = CloseRaceScenario.__new__(CloseRaceScenario)
        scenario.log = lambda *_: None
        step = SimpleNamespace(
            stage="fill_times",
            run=lambda _ctx: (_ for _ in ()).throw(RuntimeError("broken")),
        )

        with self.assertRaises(ScenarioError) as raised:
            scenario._run_step(step, object(), [])

        self.assertEqual(raised.exception.stage, "fill_times")
        self.assertEqual(raised.exception.message, "broken")
