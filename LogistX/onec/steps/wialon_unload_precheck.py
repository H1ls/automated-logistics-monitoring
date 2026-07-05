from __future__ import annotations

from LogistX.onec.steps.base_code import ensure_state, wialon_precheck_interval
from LogistX.onec.wialon_times import WialonMeta, WialonTimesPolicy, WialonTimesService
from Navigation_Bot.core.logging import normalize_log_func


class WialonUnloadPrecheckStep:
    stage = "wialon_precheck"

    def __init__(self, reportsbot=None, log_func=print, service=None, policy=None):
        self.log = normalize_log_func(log_func)
        self.service = service or WialonTimesService(reportsbot, log_func=self.log)
        self.policy = policy or WialonTimesPolicy(log_func=self.log)

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
        state = ensure_state(ctx)
        meta = WialonMeta.from_context(ctx, require_load_zone=False)
        date_from, date_to = wialon_precheck_interval(days_back=2)
        raw_payload = self.service.fetch_unload_precheck(meta, date_from, date_to)
        payload = self.policy.apply(raw_payload)
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
