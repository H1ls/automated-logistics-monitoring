from __future__ import annotations

import re
from datetime import date, datetime, timedelta

ONEC_DATETIME_FORMATS = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M")

WIALON_MONTHS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def ensure_state(ctx) -> dict:
    if not hasattr(ctx, "state") or ctx.state is None:
        ctx.state = {}
    return ctx.state


def ensure_state_dict(ctx, key: str) -> dict:
    state = ensure_state(ctx)
    value = state.get(key)
    if not isinstance(value, dict):
        value = {}
        state[key] = value
    return value


def ensure_progress(ctx) -> dict:
    return ensure_state_dict(ctx, "onec_progress")


def parse_dt(value: str | datetime | date | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    value = (value or "").strip()
    if not value:
        return None

    candidates = (value[:19], value[:16])
    for item in candidates:
        for fmt in ONEC_DATETIME_FORMATS:
            try:
                return datetime.strptime(item, fmt)
            except ValueError:
                pass
    return None


def require_dt(value: str | datetime | date | None, label: str = "datetime") -> datetime:
    parsed = parse_dt(value)
    if parsed is None:
        raise ValueError(f"Не удалось распарсить {label}: {value!r}")
    return parsed


def minute_floor(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def fmt_dt_1c(value: str | datetime | date | None) -> str:
    if isinstance(value, (datetime, date)):
        dt = require_dt(value)
        return f"{fmt_date(dt)} {fmt_time(dt)}"

    value = (value or "").strip()
    return value[:16] if len(value) >= 16 else value


def fmt_dt_minute(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def fmt_wialon(dt: datetime) -> str:
    return f"{dt.day:02d} {WIALON_MONTHS[dt.month]} {dt.year} {dt:%H:%M}"


def parse_race_dt(race_name: str) -> datetime | None:
    text = (race_name or "").strip()
    match = re.search(r"от\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{1,2}:\d{2})(?::\d{2})?", text)
    if not match:
        return None
    return parse_dt(f"{match.group(1)} {match.group(2)}")


def minutes_between(start: str | datetime | date | None,
                    end: str | datetime | date | None) -> int | None:
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)
    if not start_dt or not end_dt:
        return None
    return int((end_dt - start_dt).total_seconds() // 60)


def positive_minutes_between(start: str | datetime | date | None,
                             end: str | datetime | date | None) -> int | None:
    minutes = minutes_between(start, end)
    if minutes is None or minutes < 0:
        return None
    return minutes


def round_hours_positive(total_minutes: int | None, round_up_after_minutes: int) -> int:
    if total_minutes is None or total_minutes <= 0:
        return 0
    hours = total_minutes // 60
    if total_minutes % 60 > round_up_after_minutes:
        hours += 1
    return int(hours)


def ceil_hours_positive(total_minutes: int | None) -> int:
    return round_hours_positive(total_minutes, round_up_after_minutes=0)


def round_hours_45m(total_minutes: int | None) -> int:
    return round_hours_positive(total_minutes, round_up_after_minutes=45)


def over_hours(hours: int, threshold: int) -> int:
    return max(0, int(hours) - int(threshold))


def today_end(dt: datetime | None = None) -> datetime:
    dt = dt or datetime.now()
    return dt.replace(hour=23, minute=59, second=0, microsecond=0)


def wialon_trip_interval(departure_dt: str | datetime | date) -> tuple[str, str]:
    return fmt_wialon(require_dt(departure_dt, "departure_dt")), fmt_wialon(today_end())


def wialon_precheck_interval(days_back: int = 2) -> tuple[str, str]:
    now = datetime.now()
    date_from = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    return fmt_wialon(date_from), fmt_wialon(today_end(now))


def replace_focused_field(session, value: str, submit: bool = False, after_sleep: float = 0.15) -> None:
    session.sleep(0.08)
    session.press("f2")
    session.sleep(0.08)
    session.replace_current_field(value, submit=submit)
    session.sleep(after_sleep)
