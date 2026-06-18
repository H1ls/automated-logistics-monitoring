from __future__ import annotations

from datetime import datetime, timedelta

from LogistX.onec.steps.base_code import ensure_state, parse_dt, wialon_trip_interval


class FetchWialonTimesStep:
    stage = "fetch_wialon_times"

    def __init__(self, reportsbot, log_func=print, unload_out_guard_minutes: int = 20):
        self.unload_out_guard_minutes = int(unload_out_guard_minutes)
        self.reportsbot = reportsbot
        self.log = log_func

    @staticmethod
    def _read_wialon_meta(ctx, require_load_zone: bool = True) -> tuple[str, str, str]:
        unit = str(ctx.meta.get("unit", "") or "").strip()
        load_zone = str(ctx.meta.get("load_zone", "") or "").strip()
        unload_zone = str(ctx.meta.get("unload_zone", "") or "").strip()

        if not unit:
            raise RuntimeError("Не задан unit для Wialon")
        if require_load_zone and not load_zone:
            raise RuntimeError("Не задана geofence погрузки")
        if not unload_zone:
            raise RuntimeError("Не задана geofence выгрузки")

        return unit, load_zone, unload_zone

    def _apply_unload_out_guard(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return payload or {}

        unload_out_dt = parse_dt(payload.get("unload_out"))
        if not unload_out_dt:
            return payload

        now_dt = datetime.now()
        delta = now_dt - unload_out_dt

        if timedelta(0) <= delta < timedelta(minutes=self.unload_out_guard_minutes):
            self.log(
                f"⏳ unload_out={unload_out_dt:%d.%m.%Y %H:%M:%S} "
                f"слишком близко к now={now_dt:%d.%m.%Y %H:%M:%S} "
                f"(< {self.unload_out_guard_minutes} мин) - считаю, что машина еще на выгрузке"
            )
            payload["unload_out"] = ""

        return payload

    def fetch_trip_payload(self, ctx, date_from: str, date_to: str) -> dict:
        unit, load_zone, unload_zone = self._read_wialon_meta(ctx, require_load_zone=True)

        self.log(
            f"🌍 Wialon: unit={unit},load_zone={load_zone},unload_zone={unload_zone},from={date_from}, to={date_to}")

        payload = self.reportsbot.run_geo_report_for_trip(
            unit=unit,
            date_from=date_from,
            date_to=date_to,
            load_zone=load_zone,
            unload_zone=unload_zone,
            template="Crossing geozones",
        )
        return self._apply_unload_out_guard(payload)

    def fetch_unload_precheck_payload(self, ctx, date_from: str, date_to: str) -> dict:
        unit, load_zone, unload_zone = self._read_wialon_meta(ctx, require_load_zone=False)

        self.log(
            f"🌍 Wialon PRECHECK: unit={unit}, "
            f"load_zone={load_zone}, unload_zone={unload_zone}, "
            f"from={date_from}, to={date_to}"
        )

        payload = self.reportsbot.run_geo_report_precheck_unload(
            unit=unit,
            date_from=date_from,
            date_to=date_to,
            unload_zone=unload_zone,
            template="Пересечение гео",
        )
        return self._apply_unload_out_guard(payload or {})

    def run(self, ctx):
        if self.reportsbot is None:
            raise RuntimeError("reportsbot не передан в сценарий")
        if not ctx.departure_dt:
            raise RuntimeError("Не задан departure_dt для Wialon")

        date_from, date_to = wialon_trip_interval(ctx.departure_dt)

        payload = self.fetch_trip_payload(ctx, date_from, date_to)
        self.log(f"📦 Wialon payload: {payload}")

        ctx.load_in = payload.get("load_in", "") or None
        ctx.load_out = payload.get("load_out", "") or None
        ctx.unload_in = payload.get("unload_in", "") or None
        ctx.unload_out = payload.get("unload_out", "") or None

        ensure_state(ctx)["wialon_payload"] = payload
