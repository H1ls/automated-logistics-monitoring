# LogistX/onec/scenarios/close_race.py
from __future__ import annotations

from LogistX.onec.results import BotResult
from LogistX.onec.scenarios.base import BaseScenario, ScenarioError
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
from LogistX.onec.steps.fetch_wialon_times import FetchWialonTimesStep
from LogistX.onec.steps.fill_departure import FillDepartureStep
from LogistX.onec.steps.fill_times import FillTimesStep
from LogistX.onec.steps.find_race import FindRaceStep
from LogistX.onec.steps.open_race import OpenRaceStep
from LogistX.onec.steps.driver_rating import DriverRatingStep

class CloseRaceScenario(BaseScenario):
    name = "close_race"

    def __init__(self, session, error_handler, reportsbot, log_func=print):
        super().__init__(session, error_handler, log_func=log_func)
        self.steps = [FindRaceStep(session, error_handler, log_func),
                      OpenRaceStep(session, error_handler, log_func),
                      CaptureRaceUiStep(session, error_handler, log_func),
                      FillDepartureStep(session, error_handler, log_func),
                      FetchWialonTimesStep(reportsbot, log_func),
                      FillTimesStep(session, error_handler, log_func),
                      DriverRatingStep(session, error_handler, log_func),
                      # SubmitStep(session, error_handler, log_func),
                      ]

    def run(self, ctx) -> BotResult:
        completed = []
        try:
            for step in self.steps:
                self.log(f"\n=== STEP: {step.stage} ===")
                step.run(ctx)
                completed.append(step.stage)

            return BotResult.success(stage="done", message=f"Выполнены шаги: {', '.join(completed)}")

        except ScenarioError as e:
            self.errors.safe_abort(e.message)
            return BotResult.fail(stage=e.stage, message=e.message)
        except Exception as e:
            self.errors.safe_abort(str(e))
            return BotResult.fail(stage="unknown", message=str(e))
