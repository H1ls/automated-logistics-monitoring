from __future__ import annotations

from LogistX.onec.steps.base_code import ensure_state, wialon_trip_interval
from LogistX.onec.wialon_times import WialonMeta, WialonTimesPolicy, WialonTimesService
from Navigation_Bot.core.logging import normalize_log_func


class FetchWialonTimesStep:
    stage = "fetch_wialon_times"

    def __init__(self, reportsbot=None, log_func=print, unload_out_guard_minutes: int = 20,
                 service=None, policy=None):
        self.log = normalize_log_func(log_func)
        self.service = service or WialonTimesService(reportsbot, log_func=self.log)
        self.policy = policy or WialonTimesPolicy(
            unload_out_guard_minutes=unload_out_guard_minutes,
            log_func=self.log,
        )

    @staticmethod
    def _apply_to_context(ctx, payload: dict) -> None:
        ctx.load_in = payload.get("load_in") or None
        ctx.load_out = payload.get("load_out") or None
        ctx.unload_in = payload.get("unload_in") or None
        ctx.unload_out = payload.get("unload_out") or None
        state = ensure_state(ctx)
        state["wialon_payload"] = payload
        state["wialon_has_times"] = any([ctx.load_in, ctx.load_out, ctx.unload_in, ctx.unload_out])
        state["wialon_has_complete_payload"] = all([ctx.load_in, ctx.load_out, ctx.unload_in, ctx.unload_out])

    def run(self, ctx):
        if not ctx.departure_dt:
            raise RuntimeError("Не задан departure_dt для Wialon")

        meta = WialonMeta.from_context(ctx, require_load_zone=True)
        date_from, date_to = wialon_trip_interval(ctx.departure_dt)
        raw_payload = self.service.fetch_trip(meta, date_from, date_to)
        payload = self.policy.apply(raw_payload)

        self.log(f"📦 Wialon payload: {payload}")
        self._apply_to_context(ctx, payload)
