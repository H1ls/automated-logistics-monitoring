from __future__ import annotations

from dataclasses import dataclass

from LogistX.onec.steps.base_code import (
    ceil_hours_positive,
    over_hours,
    parse_dt,
    positive_minutes_between,
    round_hours_45m,
)


@dataclass(frozen=True)
class TripTimeInput:
    load_in: str | None = None
    load_out: str | None = None
    unload_in: str | None = None
    unload_out: str | None = None
    load_arrive_deadline: str | None = None
    unload_arrive_deadline: str | None = None


class TripTimeCalculator:
    """Чистый расчёт опозданий, стоянок и отклонений в рейтинге водителей."""

    LOAD_LATE = "Опоздание на погрузку"
    UNLOAD_LATE = "Опоздание на разгрузку"
    LOAD_STAY = "Простой на погрузке"
    UNLOAD_STAY = "Простой на разгрузке"

    def __init__(self, free_stay_hours: int = 6, min_stay_deviation_hours: int = 2):
        self.free_stay_hours = int(free_stay_hours)
        self.min_stay_deviation_hours = int(min_stay_deviation_hours)

    @staticmethod
    def _lateness_minutes(fact_arrive: str | None, deadline_arrive: str | None) -> int | None:
        fact_dt = parse_dt(fact_arrive)
        deadline_dt = parse_dt(deadline_arrive)
        if not fact_dt or not deadline_dt:
            return None
        minutes = positive_minutes_between(deadline_dt, fact_dt)
        return minutes if minutes is not None else 0

    @staticmethod
    def _stay_minutes(arrive: str | None, depart: str | None) -> int | None:
        return positive_minutes_between(arrive, depart)

    @staticmethod
    def _item(kind: str, hours: int) -> dict:
        return {"kind": kind, "hours": int(hours)}

    def calculate(self, source: TripTimeInput) -> dict:
        load_lateness_minutes = self._lateness_minutes(source.load_in, source.load_arrive_deadline)
        unload_lateness_minutes = self._lateness_minutes(source.unload_in, source.unload_arrive_deadline)
        load_stay_minutes = self._stay_minutes(source.load_in, source.load_out)
        unload_stay_minutes = self._stay_minutes(source.unload_in, source.unload_out)

        load_late_hours = ceil_hours_positive(load_lateness_minutes)
        unload_late_hours = ceil_hours_positive(unload_lateness_minutes)
        load_stay_hours = round_hours_45m(load_stay_minutes)
        unload_stay_hours = round_hours_45m(unload_stay_minutes)
        load_over_hours = over_hours(load_stay_hours, self.free_stay_hours)
        unload_over_hours = over_hours(unload_stay_hours, self.free_stay_hours)

        items = []
        if load_late_hours > 0:
            items.append(self._item(self.LOAD_LATE, load_late_hours))
        if unload_late_hours > 0:
            items.append(self._item(self.UNLOAD_LATE, unload_late_hours))
        if load_over_hours >= self.min_stay_deviation_hours:
            items.append(self._item(self.LOAD_STAY, load_over_hours))
        if unload_over_hours >= self.min_stay_deviation_hours:
            items.append(self._item(self.UNLOAD_STAY, unload_over_hours))

        return {
            "load_arrive_deadline": source.load_arrive_deadline,
            "unload_arrive_deadline": source.unload_arrive_deadline,
            "load_lateness_minutes": load_lateness_minutes,
            "unload_lateness_minutes": unload_lateness_minutes,
            "load_late_hours": load_late_hours,
            "unload_late_hours": unload_late_hours,
            "load_stay_minutes": load_stay_minutes,
            "unload_stay_minutes": unload_stay_minutes,
            "load_stay_hours": load_stay_hours,
            "unload_stay_hours": unload_stay_hours,
            "load_over_6h_hours": load_over_hours,
            "unload_over_6h_hours": unload_over_hours,
            "driver_rating_items": items,
        }
