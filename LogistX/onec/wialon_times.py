from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from LogistX.onec.steps.base_code import parse_dt
from Navigation_Bot.core.logging import normalize_log_func


@dataclass(frozen=True)
class WialonMeta:
    unit: str
    load_zone: str
    unload_zone: str

    @classmethod
    def from_context(cls, ctx, *, require_load_zone: bool = True) -> "WialonMeta":
        meta = getattr(ctx, "meta", {}) or {}
        unit = str(meta.get("unit") or "").strip()
        load_zone = str(meta.get("load_zone") or "").strip()
        unload_zone = str(meta.get("unload_zone") or "").strip()

        if not unit:
            raise RuntimeError("Не задан unit для Wialon")
        if require_load_zone and not load_zone:
            raise RuntimeError("Не задана geofence погрузки")
        if not unload_zone:
            raise RuntimeError("Не задана geofence выгрузки")
        return cls(unit=unit, load_zone=load_zone, unload_zone=unload_zone)


class WialonTimesService:
    """Получает данные отчёта Wialon """

    def __init__(self, reportsbot, log_func=print):
        self.reportsbot = reportsbot
        self.log = normalize_log_func(log_func)

    def _require_reportsbot(self) -> None:
        if self.reportsbot is None:
            raise RuntimeError("reportsbot не передан в сценарий")

    def fetch_trip(self, meta: WialonMeta, date_from: str, date_to: str) -> dict:
        self._require_reportsbot()
        self.log(f"🌍 Wialon: unit={meta.unit}, load_zone={meta.load_zone}, "
                 f"unload_zone={meta.unload_zone}, from={date_from}, to={date_to}")

        return self.reportsbot.run_geo_report_for_trip(unit=meta.unit,
                                                       date_from=date_from,
                                                       date_to=date_to,
                                                       load_zone=meta.load_zone,
                                                       unload_zone=meta.unload_zone,
                                                       template="Crossing geozones")

    def fetch_unload_precheck(self, meta: WialonMeta, date_from: str, date_to: str) -> dict:
        self._require_reportsbot()
        self.log(f"🌍 Wialon PRECHECK: unit={meta.unit}, load_zone={meta.load_zone}, "
                 f"unload_zone={meta.unload_zone}, from={date_from}, to={date_to}")

        return self.reportsbot.run_geo_report_precheck_unload(unit=meta.unit,
                                                              date_from=date_from,
                                                              date_to=date_to,
                                                              unload_zone=meta.unload_zone,
                                                              template="Пересечение гео")


class WialonTimesPolicy:
    TIME_KEYS = ("load_in", "load_out", "unload_in", "unload_out")

    def __init__(self, unload_out_guard_minutes: int = 20, log_func=print, now_func=None):
        self.unload_out_guard_minutes = int(unload_out_guard_minutes)
        self.log = normalize_log_func(log_func)
        self.now_func = now_func or datetime.now

    @staticmethod
    def _validate_pair(payload: dict, in_key: str, out_key: str) -> None:
        time_in = parse_dt(payload.get(in_key))
        time_out = parse_dt(payload.get(out_key))
        if time_out and not time_in:
            raise RuntimeError(f"Wialon: {out_key} задан без {in_key}")
        if time_in and time_out and time_out < time_in:
            raise RuntimeError(f"Wialon: {out_key} раньше {in_key}")

    def apply(self, payload: dict | None) -> dict:
        if payload is None:
            result = {}
        elif not isinstance(payload, dict):
            raise TypeError(f"Wialon payload должен быть dict, получен {type(payload).__name__}")
        else:
            result = dict(payload)

        for key in self.TIME_KEYS:
            value = result.get(key)
            if value and parse_dt(value) is None:
                raise RuntimeError(f"Wialon: некорректное время {key}={value!r}")

        self._validate_pair(result, "load_in", "load_out")
        self._validate_pair(result, "unload_in", "unload_out")

        unload_out = parse_dt(result.get("unload_out"))
        if unload_out:
            now = self.now_func()
            delta = now - unload_out
            if unload_out > now:
                self.log(f"⚠️ unload_out={unload_out:%d.%m.%Y %H:%M:%S} находится в будущем "
                         f"относительно now={now:%d.%m.%Y %H:%M:%S} — закрытие рейса заблокировано")
                result["unload_out"] = ""
            elif timedelta(0) <= delta < timedelta(minutes=self.unload_out_guard_minutes):
                self.log(f"⏳ unload_out={unload_out:%d.%m.%Y %H:%M:%S} слишком близко к "
                         f"now={now:%d.%m.%Y %H:%M:%S} (< {self.unload_out_guard_minutes} мин) — "
                         f"считаю, что машина еще на выгрузке" )
                result["unload_out"] = ""

        return result
