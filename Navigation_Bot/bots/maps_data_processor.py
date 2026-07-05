import re
from datetime import datetime, timedelta

from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint


class MapsDataProcessor:
    SHORT_ROUTE_KM = 1.0
    AVERAGE_SPEED_KMH = 66
    MONTHS = {
        "января": 1,
        "февраля": 2,
        "марта": 3,
        "апреля": 4,
        "мая": 5,
        "июня": 6,
        "июля": 7,
        "августа": 8,
        "сентября": 9,
        "октября": 10,
        "ноября": 11,
        "декабря": 12,
    }

    @staticmethod
    def parse_datetime(date_str: str, time_str: str) -> datetime | None:
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            except Exception:
                return None

    @staticmethod
    def parse_route_point(point: RoutePoint | None) -> tuple[str, datetime | None, str | None]:
        if point is None:
            return "", None, "⚠️ Пропуск: unload_point отсутствует."

        address = (point.address or "").strip()
        date_str = (point.date or "").strip()
        time_str = (point.time or "").strip()

        if not address or not date_str or not time_str:
            return "", None, "⚠️ Пропуск: неполные данные о выгрузке."

        unload_dt = MapsDataProcessor.parse_datetime(date_str, time_str)
        return address, unload_dt, None

    @staticmethod
    def duration_to_minutes(time_str: str) -> int:
        """Преобразует '2 дн. 3 ч 41 мин' в минуты."""
        try:
            time_str = time_str.strip().lower().replace("~", "")
            pattern = r"(?:(\d+)\s*дн\.)?\s*(?:(\d+)\s*ч)?\s*(?:(\d+)\s*мин)?"
            match = re.search(pattern, time_str)
            if not match:
                raise ValueError("Неверный формат")

            days = int(match.group(1)) if match.group(1) else 0
            hours = int(match.group(2)) if match.group(2) else 0
            minutes = int(match.group(3)) if match.group(3) else 0

            return days * 1440 + hours * 60 + minutes
        except Exception as e:
            raise ValueError(f"Ошибка разбора времени: {time_str} -> {e}") from e

    @classmethod
    def calculate_average_route(cls, routes: list[dict]) -> tuple[int, int]:
        times = [cls.duration_to_minutes(route["duration"]) for route in routes]
        distances = [route["distance"] for route in routes]
        return round(sum(times) / len(times)), round(sum(distances) / len(distances))

    @classmethod
    def parse_yandex_arrival(cls, text: str, year: int) -> datetime | None:
        """Парсит 'Прибытие 3 июля, в 06:14' как локальное время точки назначения."""
        text = (text or "").strip().lower().replace("\xa0", " ")
        match = re.search(r"(\d{1,2})\s+([а-яё]+),?\s+в\s+(\d{1,2}):(\d{2})", text)
        if not match:
            return None

        day = int(match.group(1))
        month = cls.MONTHS.get(match.group(2))
        if not month:
            return None

        hour = int(match.group(3))
        minute = int(match.group(4))
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None

    @staticmethod
    def parse_yandex_msk_offset(text: str) -> int | None:
        text = (text or "").strip().replace("\xa0", " ")
        match = re.search(r"\(\s*МСК\s*([+-]\s*\d{1,2})\s*\)", text, flags=re.IGNORECASE)
        if not match:
            return None
        return int(match.group(1).replace(" ", ""))

    @staticmethod
    def format_msk_offset(offset_hours: int | None) -> str:
        if offset_hours is None:
            return ""
        sign = "+" if offset_hours >= 0 else ""
        return f"МСК {sign}{offset_hours}"

    @classmethod
    def calculate_average_arrival(cls, routes: list[dict], deadline: datetime) -> datetime | None:
        arrivals = [
            cls._parse_yandex_arrival_near_deadline(str(route.get("arrival", "")), deadline)
            for route in routes
        ]
        arrivals = [arrival for arrival in arrivals if arrival is not None]
        if not arrivals:
            return None

        anchor = datetime(1970, 1, 1)
        avg_seconds = sum((arrival - anchor).total_seconds() for arrival in arrivals) / len(arrivals)
        rounded_seconds = round(avg_seconds / 60) * 60
        return anchor + timedelta(seconds=rounded_seconds)

    @classmethod
    def calculate_arrival_timezone_offset(cls, routes: list[dict]) -> int | None:
        offsets = [
            cls.parse_yandex_msk_offset(str(route.get("arrival", "")))
            for route in routes
        ]
        offsets = [offset for offset in offsets if offset is not None]
        if not offsets:
            return None

        return max(offsets, key=offsets.count)

    @classmethod
    def _parse_yandex_arrival_near_deadline(cls, text: str, deadline: datetime) -> datetime | None:
        candidates = [cls.parse_yandex_arrival(text, deadline.year - 1),
                      cls.parse_yandex_arrival(text, deadline.year),
                      cls.parse_yandex_arrival(text, deadline.year + 1) ]
        candidates = [candidate for candidate in candidates if candidate is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: abs(candidate - deadline))

    @classmethod
    def calculate_arrival_time(cls, distance_km: float, now: datetime | None = None) -> datetime:
        base_time = now or datetime.now()
        return base_time + timedelta(hours=distance_km / cls.AVERAGE_SPEED_KMH)

    @staticmethod
    def get_arrival_result(arrival_time: datetime, unload_dt: datetime | None,
                           timezone_offset_hours: int | None = None) -> dict:
        if unload_dt:
            buffer = unload_dt - arrival_time
            total_minutes = int(buffer.total_seconds() // 60)
        else:
            total_minutes = 0

        buf_hours = total_minutes // 60
        buf_minutes = total_minutes % 60

        return {
            "время прибытия": arrival_time.strftime("%d.%m.%Y %H:%M"),
            "время разгрузки": unload_dt.strftime("%d.%m.%Y %H:%M") if unload_dt else "Не указано",
            "on_time": bool(unload_dt and arrival_time <= unload_dt),
            "time_buffer": f"{buf_hours}ч {buf_minutes}м",
            "buffer_minutes": total_minutes,
            "timezone": MapsDataProcessor.format_msk_offset(timezone_offset_hours),
            "timezone_offset_hours": timezone_offset_hours,
        }

    @staticmethod
    def apply_short_route_result(car: dict, now: datetime | None = None) -> None:
        car["гео"] = "у выгрузки"
        car["коор"] = ""
        car["скорость"] = 0

        arrival = (now or datetime.now()).strftime("%d.%m.%Y %H:%M")
        car["Маршрут"] = {
            "расстояние": "0.0 км",
            "длительность": "0 мин",
            "время прибытия": arrival,
            "успеет": True,
            "time_buffer": "—",
        }

    @staticmethod
    def apply_route_result(car: dict, result: dict, avg_distance: float, avg_minutes: float) -> None:
        car["Маршрут"] = {
            "расстояние": f"{avg_distance} км",
            "длительность": f"{avg_minutes} мин",
            "время прибытия": result["время прибытия"],
            "успеет": result["on_time"],
            "time_buffer": result["time_buffer"],
            "buffer_minutes": result["buffer_minutes"],
        }
        if result.get("timezone"):
            car["Маршрут"]["timezone"] = result["timezone"]
            car["Маршрут"]["timezone_offset_hours"] = result["timezone_offset_hours"]
