# LogistX/onec/scenarios/close_race.py
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timedelta

from LogistX.onec.results import BotResult
from LogistX.onec.scenarios.base import BaseScenario, ScenarioError
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
from LogistX.onec.steps.fetch_wialon_times import FetchWialonTimesStep
from LogistX.onec.steps.fill_departure import FillDepartureStep
from LogistX.onec.steps.fill_times import FillTimesStep
from LogistX.onec.steps.find_race import FindRaceStep
from LogistX.onec.steps.open_race import OpenRaceStep
from LogistX.onec.steps.driver_rating import DriverRatingStep
from LogistX.onec.steps.submit import SubmitStep


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
        self.fetch_wialon_times_step = FetchWialonTimesStep(reportsbot, log_func)
        self.fill_times_step = FillTimesStep(session, error_handler, log_func)
        self.driver_rating_step = DriverRatingStep(session, error_handler, log_func)
        self.submit_step = SubmitStep(session, error_handler, log_func)

    def _run_step(self, step, ctx, completed: list[str]):
        self.log(f"\n=== STEP: {step.stage} ===")
        step.run(ctx)
        completed.append(step.stage)

    def run(self, ctx) -> BotResult:
        completed: list[str] = []
        precheck_future: Future | None = None
        local_executor: ThreadPoolExecutor | None = None

        try:
            self._mark_progress(ctx, race_opened=False, ui_captured=False,
                                departure_filled=False, times_filled=False,
                                driver_rating_filled=False, submitted=False)

            self._run_step(self.find_race_step, ctx, completed)

            self._run_step(self.open_race_step, ctx, completed)
            self._mark_progress(ctx, race_opened=True)

            # Стартуем быстрый Wialon precheck сразу после открытия рейса
            self.log("\n=== STEP: wialon_precheck[start] ===")
            precheck_future, local_executor = self._start_precheck(ctx)

            # Пока Selenium ищет по Wialon — работаем дальше в 1С
            self._run_step(self.capture_ui_step, ctx, completed)
            self._mark_progress(ctx, ui_captured=True)

            self._run_step(self.fill_departure_step, ctx, completed)
            self._mark_progress(ctx, departure_filled=bool(ctx.departure_dt))

            # Здесь ждём результат precheck
            self.log("\n=== STEP: wialon_precheck[wait] ===")
            precheck = precheck_future.result() if precheck_future else self._run_unload_precheck(ctx)

            status = precheck.get("status")

            if status == "in_transit":
                return BotResult.success(stage="wialon_precheck",
                                         message="Рейс не закрыт: ещё в пути", )

            if status == "on_unload":
                return BotResult.success(stage="wialon_precheck",
                                         message="Рейс не закрыт: ещё на выгрузке", )

            self._run_step(self.fetch_wialon_times_step, ctx, completed)

            self._run_step(self.fill_times_step, ctx, completed)
            self._mark_progress(ctx, times_filled=True)

            self._run_step(self.driver_rating_step, ctx, completed)
            self._mark_progress(ctx, driver_rating_filled=True)

            # self._run_step(self.submit_step, ctx, completed)
            self._mark_progress(ctx, submitted=True)

            ctx.state["close_status"] = "closed"

            return BotResult.success(stage="done",
                                     message=f"Выполнены шаги: {', '.join(completed)}")

        except ScenarioError as e:
            self.errors.safe_abort(e.message)
            return BotResult.fail(stage=e.stage, message=e.message)

        except Exception as e:
            self.errors.safe_abort(str(e))
            return BotResult.fail(stage="unknown", message=str(e))

        finally:
            if local_executor:
                local_executor.shutdown(wait=False)

    # TODO: Вынести все кроме _run_step, run

    @staticmethod
    def _ensure_state(ctx):
        if not hasattr(ctx, "state") or ctx.state is None:
            ctx.state = {}
        return ctx.state

    def _build_precheck_interval(self) -> tuple[str, str]:
        """Интервал: now - 2 days @ 00:00
                     now @ 23:59"""
        now = datetime.now()

        date_from_dt = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        date_to_dt = now.replace(hour=23, minute=59, second=0, microsecond=0)

        return (FetchWialonTimesStep.fmt_wialon(date_from_dt),
                FetchWialonTimesStep.fmt_wialon(date_to_dt),)

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        value = (value or "").strip()
        if not value:
            return None

        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        return None

    def _apply_unload_out_guard_for_precheck(self, payload: dict, guard_minutes: int = 20) -> dict:
        """
        Если unload_out слишком свежий, считаем что машина еще на выгрузке.
        Уже есть в FetchWialonTimesStep.run().
        """
        if not isinstance(payload, dict):
            return payload or {}

        unload_out_str = payload.get("unload_out")
        unload_out_dt = self._parse_dt(unload_out_str)
        if not unload_out_dt:
            return payload

        now_dt = datetime.now()
        delta = now_dt - unload_out_dt

        if timedelta(0) <= delta < timedelta(minutes=guard_minutes):
            self.log(f"⏳ PRECHECK guard: unload_out={unload_out_dt:%d.%m.%Y %H:%M:%S} "
                     f"слишком близко к now={now_dt:%d.%m.%Y %H:%M:%S} "
                     f"(< {guard_minutes} мин) — считаю, что машина ещё на выгрузке")
            payload["unload_out"] = ""

        return payload

    def _run_unload_precheck(self, ctx) -> dict:
        if self.reportsbot is None:
            raise RuntimeError("reportsbot не передан в сценарий")

        state = self._ensure_state(ctx)

        unit = str(ctx.meta.get("unit", "") or "").strip()
        load_zone = str(ctx.meta.get("load_zone", "") or "").strip()
        unload_zone = str(ctx.meta.get("unload_zone", "") or "").strip()

        if not unit:
            raise RuntimeError("Не задан unit для Wialon precheck")
        if not load_zone:
            raise RuntimeError("Не задана geofence погрузки для Wialon precheck")
        if not unload_zone:
            raise RuntimeError("Не задана geofence выгрузки для Wialon precheck")

        date_from, date_to = self._build_precheck_interval()

        self.log(f"🌍 Wialon PRECHECK: unit={unit}, "
                 f"load_zone={load_zone}, unload_zone={unload_zone}, "
                 f"from={date_from}, to={date_to}")

        payload = self.reportsbot.run_geo_report_precheck_unload(unit=unit,
                                                                 date_from=date_from,
                                                                 date_to=date_to,
                                                                 unload_zone=unload_zone,
                                                                 template="Пересечение гео", ) or {}
        payload = self._apply_unload_out_guard_for_precheck(payload, guard_minutes=20)

        unload_in = (payload.get("unload_in") or "").strip()
        unload_out = (payload.get("unload_out") or "").strip()

        if not unload_in:
            status = "in_transit"
            status_text = "ещё в пути"
        elif unload_in and not unload_out:
            status = "on_unload"
            status_text = "ещё на выгрузке"
        else:
            status = "ready_to_close"
            status_text = "можно закрывать"

        result = {"status": status,
                  "status_text": status_text,
                  "payload": payload,
                  "date_from": date_from,
                  "date_to": date_to, }

        state["mini_wialon_precheck"] = result
        state["close_status"] = status
        self.log(f"📦 PRECHECK payload: {payload}")
        self.log(f"🚦 PRECHECK status: {status} ({status_text})")

        return result

    def _start_precheck(self, ctx) -> tuple[Future | None, ThreadPoolExecutor | None]:
        """
        Запускаем precheck в отдельном потоке.
        Если внешний executor не передан — создаём локальный.
        """
        executor = self.precheck_executor
        local_executor = None

        if executor is None:
            local_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wialon-precheck")
            executor = local_executor

        future = executor.submit(self._run_unload_precheck, ctx)
        return future, local_executor

    def _mark_progress(self, ctx, **flags):
        state = self._ensure_state(ctx)
        progress = state.get("onec_progress")
        if not isinstance(progress, dict):
            progress = {}
            state["onec_progress"] = progress
        progress.update(flags)
