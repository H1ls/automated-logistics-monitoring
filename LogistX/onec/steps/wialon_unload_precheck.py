from __future__ import annotations

from LogistX.onec.steps.base_code import ensure_state, wialon_precheck_interval
from LogistX.onec.steps.fetch_wialon_times import FetchWialonTimesStep


class WialonUnloadPrecheckStep:
    stage = "wialon_precheck"

    def __init__(self, reportsbot, log_func=print, fetcher: FetchWialonTimesStep | None = None):
        self.reportsbot = reportsbot
        self.log = log_func
        self.fetcher = fetcher or FetchWialonTimesStep(reportsbot, log_func)

    @staticmethod
    def _status_from_payload(payload: dict) -> tuple[str, str]:
        unload_in = (payload.get("unload_in") or "").strip()
        unload_out = (payload.get("unload_out") or "").strip()

        if not unload_in:
            return "in_transit", "еще в пути"
        if not unload_out:
            return "on_unload", "еще на выгрузке"
        return "ready_to_close", "можно закрывать"

    def run(self, ctx) -> dict:
        if self.reportsbot is None:
            raise RuntimeError("reportsbot не передан в сценарий")

        state = ensure_state(ctx)
        date_from, date_to = wialon_precheck_interval(days_back=2)
        payload = self.fetcher.fetch_unload_precheck_payload(ctx, date_from, date_to)
        status, status_text = self._status_from_payload(payload)

        result = {
            "status": status,
            "status_text": status_text,
            "payload": payload,
            "date_from": date_from,
            "date_to": date_to,
        }

        state["mini_wialon_precheck"] = result
        state["close_status"] = status
        self.log(f"📦 PRECHECK payload: {payload}")
        self.log(f"🚦 PRECHECK status: {status} ({status_text})")

        return result
