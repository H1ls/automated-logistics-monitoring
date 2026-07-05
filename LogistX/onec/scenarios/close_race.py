from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import threading
import time

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
        self._run_started_at = 0.0

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
        self._run_started_at = time.perf_counter()

        try:
            self._mark_progress(ctx, race_opened=False, ui_captured=False, departure_filled=False, times_filled=False,
                                driver_rating_filled=False, submitted=False)

            self._run_step(self.find_race_step, ctx, completed)

            self._run_step(self.open_race_step, ctx, completed)
            self._mark_progress(ctx, race_opened=True)

            self.log("\n=== STEP: wialon_precheck[start] ===")
            precheck_future, local_executor = self._start_precheck(ctx)
            self.log(f"⏱ wialon_precheck submitted in background at +{self._elapsed():.2f}s")

            self._run_step(self.capture_ui_step, ctx, completed)
            self._mark_progress(ctx, ui_captured=True)

            self._run_step(self.fill_departure_step, ctx, completed)
            self._mark_progress(ctx, departure_filled=bool(ctx.departure_dt))
            self.log(f"⏱ FillDepartureStep result: departure_dt={ctx.departure_dt!r}")

            self.log("\n=== STEP: wialon_precheck[wait] ===")
            try:
                wait_started_at = time.perf_counter()
                precheck = precheck_future.result() if precheck_future else self.wialon_precheck_step.run(ctx)
                self.log(f"⏱ wialon_precheck wait finished in {time.perf_counter() - wait_started_at:.2f}s")
            except Exception as exc:
                raise ScenarioError(self.wialon_precheck_step.stage, str(exc)) from exc

            self._log_precheck_close_readiness(ctx, precheck)
            status = precheck.get("status")

            if status == "in_transit":
                return BotResult.success(stage="wialon_precheck", message="Рейс не закрыт: еще в пути")

            if status == "on_unload":
                return BotResult.success(stage="wialon_precheck", message="Рейс не закрыт: еще на выгрузке")

            self._run_step(self.fetch_wialon_times_step, ctx, completed)
            if not self._has_complete_wialon_payload(ctx):
                self._close_without_incomplete_wialon_payload(ctx)
                self._mark_progress(ctx, submitted=True)
                return BotResult.success(stage="fetch_wialon_times",
                                         message="Рейс закрыт без заполнения времен: Wialon вернул неполный payload")

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

        def _run_background_precheck():
            started_at = time.perf_counter()
            thread = threading.current_thread()
            self.log(f"⏱ wialon_precheck background started at +{self._elapsed():.2f}s "
                     f"thread={thread.name}/{threading.get_ident()}")
            try:
                return self.wialon_precheck_step.run(ctx)
            finally:
                self.log(f"⏱ wialon_precheck background finished in {time.perf_counter() - started_at:.2f}s "
                         f"at +{self._elapsed():.2f}s")

        future = executor.submit(_run_background_precheck)
        return future, local_executor

    def _mark_progress(self, ctx, **flags):
        ensure_progress(ctx).update(flags)

    @staticmethod
    def _has_complete_wialon_payload(ctx) -> bool:
        state = getattr(ctx, "state", {}) or {}
        if "wialon_has_complete_payload" in state:
            return bool(state["wialon_has_complete_payload"])
        return all([ctx.load_in, ctx.load_out, ctx.unload_in, ctx.unload_out])

    def _close_without_incomplete_wialon_payload(self, ctx) -> None:
        payload = (getattr(ctx, "state", {}) or {}).get("wialon_payload") or {}
        missing = [key for key in ("load_in", "load_out", "unload_in", "unload_out") if not payload.get(key)]
        self.log(f"ℹ️ Wialon payload неполный, пропускаю дальнейшие шаги: missing={missing}")
        self.session.submit_ctrl_enter()
        ctx.state["submitted"] = True
        ctx.state["close_status"] = "closed_without_complete_wialon_payload"
        ctx.state["wialon_missing_keys"] = missing

    def _log_precheck_close_readiness(self, ctx, precheck: dict | None) -> None:
        precheck = precheck or {}
        payload = precheck.get("payload") or {}
        unload_in = payload.get("unload_in") or ""
        unload_out = payload.get("unload_out") or ""
        departure_dt = getattr(ctx, "departure_dt", None) or ""
        ready = bool(departure_dt and unload_in and unload_out)
        self.log(
            "⏱ close readiness: "
            f"departure_dt={departure_dt!r}, "
            f"precheck.unload_in={unload_in!r}, "
            f"precheck.unload_out={unload_out!r}, "
            f"status={precheck.get('status')!r}, "
            f"ready={ready}"
        )

    def _elapsed(self) -> float:
        if not self._run_started_at:
            return 0.0
        return time.perf_counter() - self._run_started_at
