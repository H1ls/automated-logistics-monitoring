# LogistX/onec/steps/fetch_wialon_times.py
from __future__ import annotations

from datetime import datetime, timedelta


class FetchWialonTimesStep:
    stage = "fetch_wialon_times"

    def __init__(self, reportsbot, log_func=print, unload_out_guard_minutes: int = 20):
        self.unload_out_guard_minutes = int(unload_out_guard_minutes)
        self.reportsbot = reportsbot
        self.log = log_func

    @staticmethod
    def fmt_wialon(dt: datetime) -> str:
        months = {1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
                  5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
                  9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь", }

        return f"{dt.day:02d} {months[dt.month]} {dt.year} {dt:%H:%M}"

    @staticmethod
    def _parse_departure(value: str) -> datetime:
        return datetime.strptime(value.strip()[:16], "%d.%m.%Y %H:%M")

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

    def _apply_unload_out_guard(self, payload: dict) -> dict:
        """
        Если unload_out слишком близко к текущему времени,
        считаем, что машина ещё находится на выгрузке.
        """
        if not isinstance(payload, dict):
            return payload or {}

        unload_out_str = payload.get("unload_out")
        unload_out_dt = self._parse_dt(unload_out_str)
        if not unload_out_dt:
            return payload

        now_dt = datetime.now()
        delta = now_dt - unload_out_dt

        # unload_out в будущем или слишком свежий -> не учитываем
        if timedelta(0) <= delta < timedelta(minutes=self.unload_out_guard_minutes):
            self.log(f"⏳ unload_out={unload_out_dt:%d.%m.%Y %H:%M:%S} "
                     f"слишком близко к now={now_dt:%d.%m.%Y %H:%M:%S} "
                     f"(< {self.unload_out_guard_minutes} мин) — считаю, что машина ещё на выгрузке")
            payload["unload_out"] = ""

        return payload

    def run(self, ctx):
        if self.reportsbot is None:
            raise RuntimeError("reportsbot не передан в сценарий")

        unit = str(ctx.meta.get("unit", "") or "").strip()
        load_zone = str(ctx.meta.get("load_zone", "") or "").strip()
        unload_zone = str(ctx.meta.get("unload_zone", "") or "").strip()

        if not unit:
            raise RuntimeError("Не задан unit для Wialon")
        if not load_zone:
            raise RuntimeError("Не задана geofence погрузки")
        if not unload_zone:
            raise RuntimeError("Не задана geofence выгрузки")
        if not ctx.departure_dt:
            raise RuntimeError("Не задан departure_dt для Wialon")

        fd = self._parse_departure(ctx.departure_dt)

        now = datetime.now()
        today_end = now.replace(hour=23, minute=59, second=0, microsecond=0)

        date_from = self.fmt_wialon(fd)
        date_to = self.fmt_wialon(today_end)

        self.log(f"🌍 Wialon: unit={unit}, "
                 f"load_zone={load_zone}, unload_zone={unload_zone}, "
                 f"from={date_from}, to={date_to}")

        payload = self.reportsbot.run_geo_report_for_trip(unit=unit,
                                                          date_from=date_from,
                                                          date_to=date_to,
                                                          load_zone=load_zone,
                                                          unload_zone=unload_zone,
                                                          template="Crossing geozones", )
        payload = self._apply_unload_out_guard(payload)
        self.log(f"📦 Wialon payload: {payload}")

        ctx.load_in = payload.get("load_in", "") or None
        ctx.load_out = payload.get("load_out", "") or None
        ctx.unload_in = payload.get("unload_in", "") or None
        ctx.unload_out = payload.get("unload_out", "") or None

        ctx.state["wialon_payload"] = payload
