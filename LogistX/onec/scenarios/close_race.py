from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from LogistX.onec.results import BotResult
from LogistX.onec.scenarios.base import BaseScenario, ScenarioError
from LogistX.onec.steps.base_code import ensure_progress
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
from LogistX.onec.steps.driver_rating import DriverRatingStep
from LogistX.onec.steps.fetch_wialon_times import FetchWialonTimesStep
from LogistX.onec.steps.fill_departure import FillDepartureStep
from LogistX.onec.steps.fill_times import FillTimesStep
from LogistX.onec.steps.find_race import FindRaceStep
from LogistX.onec.steps.open_race import OpenRaceStep
from LogistX.onec.steps.submit import SubmitStep
from LogistX.onec.steps.wialon_unload_precheck import WialonUnloadPrecheckStep
from LogistX.onec.wialon_times import WialonTimesPolicy, WialonTimesService


class CloseRaceScenario(BaseScenario):
    name = "close_race"

    def __init__(self, session, error_handler, reportsbot, log_func=print, precheck_executor=None):
        super().__init__(session, error_handler, log_func=log_func)

        self.reportsbot = reportsbot
        self.precheck_executor = precheck_executor

        self.find_race_step = FindRaceStep(session, error_handler, log_func)
        self.open_race_step = OpenRaceStep(session, error_handler, log_func)
        self.capture_ui_step = CaptureRaceUiStep(session, error_handler, log_func)

        self.fill_departure_step = FillDepartureStep(session, error_handler, log_func)
        self.wialon_times_service = WialonTimesService(reportsbot, log_func=log_func)
        self.wialon_times_policy = WialonTimesPolicy(log_func=log_func)
        self.fetch_wialon_times_step = FetchWialonTimesStep(log_func=log_func,
                                                            service=self.wialon_times_service,
                                                            policy=self.wialon_times_policy)
        self.wialon_precheck_step = WialonUnloadPrecheckStep(log_func=log_func,
                                                             service=self.wialon_times_service,
                                                             policy=self.wialon_times_policy)
        self.fill_times_step = FillTimesStep(session, error_handler, log_func)
        self.driver_rating_step = DriverRatingStep(session, error_handler, log_func)
        self.submit_step = SubmitStep(session, error_handler, log_func)

    def _run_step(self, step, ctx, completed: list[str]):
        self.log(f"\n=== STEP: {step.stage} ===")
        try:
            step.run(ctx)
        except ScenarioError:
            raise
        except Exception as exc:
            raise ScenarioError(step.stage, str(exc)) from exc
        completed.append(step.stage)

    def run(self, ctx) -> BotResult:
        completed: list[str] = []
        precheck_future: Future | None = None
        local_executor: ThreadPoolExecutor | None = None

        try:
            self._mark_progress(ctx, race_opened=False, ui_captured=False, departure_filled=False, times_filled=False,
                                driver_rating_filled=False, submitted=False)

            self._run_step(self.find_race_step, ctx, completed)

            self._run_step(self.open_race_step, ctx, completed)
            self._mark_progress(ctx, race_opened=True)

            self.log("\n=== STEP: wialon_precheck[start] ===")
            precheck_future, local_executor = self._start_precheck(ctx)

            self._run_step(self.capture_ui_step, ctx, completed)
            self._mark_progress(ctx, ui_captured=True)

            self._run_step(self.fill_departure_step, ctx, completed)
            self._mark_progress(ctx, departure_filled=bool(ctx.departure_dt))

            self.log("\n=== STEP: wialon_precheck[wait] ===")
            try:
                precheck = precheck_future.result() if precheck_future else self.wialon_precheck_step.run(ctx)
            except Exception as exc:
                raise ScenarioError(self.wialon_precheck_step.stage, str(exc)) from exc

            status = precheck.get("status")

            if status == "in_transit":
                return BotResult.success(stage="wialon_precheck", message="Рейс не закрыт: еще в пути")

            if status == "on_unload":
                return BotResult.success(stage="wialon_precheck", message="Рейс не закрыт: еще на выгрузке")

            self._run_step(self.fetch_wialon_times_step, ctx, completed)

            self._run_step(self.fill_times_step, ctx, completed)
            self._mark_progress(ctx, times_filled=True)

            self._run_step(self.driver_rating_step, ctx, completed)
            self._mark_progress(ctx, driver_rating_filled=True)

            self._run_step(self.submit_step, ctx, completed)
            self._mark_progress(ctx, submitted=True)

            return BotResult.success(stage="done", message=f"Выполнены шаги: {', '.join(completed)}")

        except ScenarioError as e:
            self.errors.safe_abort(e.message)
            return BotResult.fail(stage=e.stage, message=e.message)

        except Exception as e:
            self.errors.safe_abort(str(e))
            return BotResult.fail(stage="unknown", message=str(e))

        finally:
            if local_executor:
                local_executor.shutdown(wait=False)

    def _start_precheck(self, ctx) -> tuple[Future | None, ThreadPoolExecutor | None]:
        executor = self.precheck_executor
        local_executor = None

        if executor is None:
            local_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wialon-precheck")
            executor = local_executor

        future = executor.submit(self.wialon_precheck_step.run, ctx)
        return future, local_executor

    def _mark_progress(self, ctx, **flags):
        ensure_progress(ctx).update(flags)
