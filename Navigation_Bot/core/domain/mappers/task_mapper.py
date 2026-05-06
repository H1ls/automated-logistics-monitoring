from __future__ import annotations

from typing import Any

from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.value_objects.arrival_forecast import ArrivalForecast
from Navigation_Bot.core.domain.value_objects.carrier import Carrier
from Navigation_Bot.core.domain.value_objects.driver import Driver
from Navigation_Bot.core.domain.value_objects.navigation_state import NavigationState
from Navigation_Bot.core.domain.value_objects.processing_state import ProcessingState
from Navigation_Bot.core.domain.value_objects.vehicle import Vehicle
import re

from Navigation_Bot.core.domain.value_objects.route_plan import RoutePlan
from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint


class TaskMapper:
    """
    Mapper между dict (текущий JSON) и доменной моделью Task.

    - простые поля
    - vehicle / driver / carrier
    - route_plan из Погрузка/Выгрузка
    - navigation
    - forecast из Маршрут
    - processing из processed
    """

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Task:
        if not isinstance(data, dict):
            raise ValueError("TaskMapper.from_dict: data must be dict")
        vehicle = Vehicle(plate_number=str(data.get("ТС", "") or ""),
                          monitoring_id=TaskMapper._to_int_or_none(data.get("id")),
                          )

        driver = Driver(full_name=str(data.get("ФИО", "") or ""),
                        phone=str(data.get("Телефон", "") or ""),
                        )
        carrier_name = str(data.get("КА", "") or "").strip()
        carrier = Carrier(name=carrier_name) if carrier_name else None
        processed = data.get("processed")
        if not isinstance(processed, list):
            processed = []

        processing = ProcessingState(processed_unloads=[bool(x) for x in processed])

        navigation = TaskMapper._build_navigation(data)
        forecast = TaskMapper._build_forecast(data)
        route_plan = TaskMapper._build_route_plan(data)
        task = Task(index=TaskMapper._to_int_or_zero(data.get("index")),
                    vehicle=vehicle,
                    driver=driver,
                    carrier=carrier,
                    route_plan=route_plan,
                    navigation=navigation,
                    forecast=forecast,
                    processing=processing,
                    raw_load=str(data.get("raw_load", "") or ""),
                    raw_unload=str(data.get("raw_unload", "") or ""),
                    highlight_until=data.get("highlight_until"),
                    )
        task.ensure_processing_consistency()
        return task

    @staticmethod
    def to_dict(task: Task) -> dict[str, Any]:
        if not isinstance(task, Task):
            raise ValueError("TaskMapper.to_dict: task must be Task")
        result: dict[str, Any] = {"index": task.index,
                                  "ТС": task.vehicle.plate_number,
                                  "ФИО": task.driver.full_name,
                                  "Телефон": task.driver.phone,
                                  "КА": task.carrier.name if task.carrier else "",
                                  "processed": list(task.processing.processed_unloads),
                                  }

        if task.vehicle.monitoring_id is not None:
            result["id"] = task.vehicle.monitoring_id

        if task.raw_load:
            result["raw_load"] = task.raw_load
        if task.raw_unload:
            result["raw_unload"] = task.raw_unload

        if task.highlight_until:
            result["highlight_until"] = task.highlight_until

        TaskMapper._write_navigation(result, task.navigation)
        TaskMapper._write_forecast(result, task.forecast)
        TaskMapper._write_route_plan(result, task.route_plan)

        return result

    # --- Navigation
    @staticmethod
    def _build_navigation(data: dict[str, Any]) -> NavigationState:
        gps_fix = data.get("gps_fix_age")
        gps_fix_text = ""
        gps_fix_age_seconds = None

        if isinstance(gps_fix, dict):
            gps_fix_text = str(gps_fix.get("text", "") or "")
            gps_fix_age_seconds = TaskMapper._to_int_or_none(gps_fix.get("age_second"))

        speed = data.get("скорость")
        if isinstance(speed, str) and not speed.strip():
            speed = None

        return NavigationState(
            geo_text=str(data.get("гео", "") or ""),
            coordinates=str(data.get("коор", "") or ""),
            speed_kmh=speed if isinstance(speed, (int, float)) else TaskMapper._to_number_or_none(speed),
            gps_fix_text=gps_fix_text,
            gps_fix_age_seconds=gps_fix_age_seconds,
            has_fresh_coordinates=bool(data.get("_новые_координаты", False)), )

    @staticmethod
    def _write_navigation(result: dict[str, Any], navigation: NavigationState) -> None:
        if navigation.geo_text:
            result["гео"] = navigation.geo_text
        if navigation.coordinates:
            result["коор"] = navigation.coordinates
        if navigation.speed_kmh is not None:
            result["скорость"] = navigation.speed_kmh

        if navigation.gps_fix_text or navigation.gps_fix_age_seconds is not None:
            result["gps_fix_age"] = {"text": navigation.gps_fix_text,
                                     "age_second": navigation.gps_fix_age_seconds, }

        result["_новые_координаты"] = bool(navigation.has_fresh_coordinates)

    # === Forecast / Маршрут
    @staticmethod
    def _build_forecast(data: dict[str, Any]) -> ArrivalForecast:
        route = data.get("Маршрут")
        if not isinstance(route, dict):
            return ArrivalForecast()

        return ArrivalForecast(distance_km=TaskMapper._parse_distance_km(route.get("расстояние")),
                               duration_minutes=TaskMapper._parse_duration_minutes(route.get("длительность")),
                               arrival_time=str(route.get("время прибытия", "") or ""),
                               on_time=bool(route.get("успеет", False)),
                               time_buffer_text=str(route.get("time_buffer", "") or ""),
                               buffer_minutes=TaskMapper._to_int_or_zero(route.get("buffer_minutes")), )

    @staticmethod
    def _write_forecast(result: dict[str, Any], forecast: ArrivalForecast) -> None:

        has_forecast = bool(forecast.arrival_time
                            or forecast.time_buffer_text
                            or forecast.distance_km is not None
                            or forecast.duration_minutes is not None
                            )
        if not has_forecast:
            return

        result["Маршрут"] = {"расстояние": f"{forecast.distance_km} км",
                             "длительность": f"{forecast.duration_minutes} мин",
                             "время прибытия": forecast.arrival_time,
                             "успеет": forecast.on_time,
                             "time_buffer": forecast.time_buffer_text,
                             "buffer_minutes": forecast.buffer_minutes, }

    # === Helpers
    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        return None

    @staticmethod
    def _to_int_or_zero(value: Any) -> int:
        parsed = TaskMapper._to_int_or_none(value)
        return parsed if parsed is not None else 0

    @staticmethod
    def _to_number_or_none(value: Any) -> int | float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value

        text = str(value).strip().replace(",", ".")
        if not text:
            return None

        try:
            number = float(text)
        except ValueError:
            return None

        return int(number) if number.is_integer() else number

    @staticmethod
    def _parse_distance_km(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip().lower().replace(",", ".").replace("км", "").strip()
        try:
            return float(text)
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_duration_minutes(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)

        text = str(value).strip().lower().replace("мин", "").strip()
        try:
            return int(float(text))
        except ValueError:
            return 0

    # === RoutePlan / Погрузка / Выгрузка
    @staticmethod
    def _build_route_plan(data: dict[str, Any]) -> RoutePlan:
        loads = TaskMapper._parse_points(data.get("Погрузка"), kind="load", prefix="Погрузка")
        unloads = TaskMapper._parse_points(data.get("Выгрузка"), kind="unload", prefix="Выгрузка")
        return RoutePlan(loads=loads, unloads=unloads)

    @staticmethod
    def _write_route_plan(result: dict[str, Any], route_plan: RoutePlan) -> None:
        result["Погрузка"] = TaskMapper._points_to_legacy_blocks(route_plan.loads, prefix="Погрузка", )
        result["Выгрузка"] = TaskMapper._points_to_legacy_blocks(route_plan.unloads, prefix="Выгрузка", )

    @staticmethod
    def _parse_points(raw_blocks: Any, kind: str, prefix: str) -> list[RoutePoint]:
        if not isinstance(raw_blocks, list):
            return []

        points: list[RoutePoint] = []
        comment_blocks: list[tuple[int, str]] = []  # (position, comment)

        for idx, block in enumerate(raw_blocks):
            if not isinstance(block, dict):
                continue

            # Читаем комментарий если есть
            comment = str(block.get("Комментарий", "") or "").strip()

            # Проверяем: это блок ТОЛЬКО с комментарием (без адреса)?
            has_address_key = any(k != "Комментарий" and k for k in block.keys())

            if not has_address_key and comment:
                # Чистый комментарий — запоминаем позицию
                comment_blocks.append((idx, comment))
                continue

            # Обычный блок с адресом
            seq = TaskMapper._extract_sequence_from_block(block, prefix)
            if seq is None:
                # Нет ключа "Погрузка N" — используем позицию как sequence
                seq = idx + 1

            address = str(block.get(f"{prefix} {seq}", "") or "").strip()
            date = str(block.get(f"Дата {seq}", "") or "").strip()
            time = str(block.get(f"Время {seq}", "") or "").strip()

            if not address and not date and not time and not comment:
                continue

            points.append(RoutePoint(kind=kind,
                                     sequence=seq,
                                     address=address,
                                     date=date,
                                     time=time,
                                     comment=comment, ))

        # Добавляем comment-only блоки как отдельные точки
        for pos, comment in comment_blocks:
            points.append(RoutePoint(kind=kind,
                                     sequence=pos + 1000,  # большой offset чтобы не конфликтовать
                                     address="",
                                     date="",
                                     time="",
                                     comment=comment, )
                          )

        points.sort(key=lambda p: p.sequence)
        return points

    @staticmethod
    def _points_to_legacy_blocks(points: list[RoutePoint], prefix: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []

        for i, point in enumerate(points, start=1):
            if point.sequence >= 1000:
                if point.comment:
                    result.append({"Комментарий": point.comment})
                continue

            seq = point.sequence if point.sequence > 0 else i

            block = {f"{prefix} {seq}": point.address,
                     f"Дата {seq}": point.date,
                     f"Время {seq}": point.time, }

            result.append(block)

            # комментарий рядом с точкой
            if point.comment:
                result.append({"Комментарий": point.comment})

        return result

    @staticmethod
    def _extract_sequence_from_block(block: dict[str, Any], prefix: str) -> int | None:
        pattern = re.compile(rf"^{re.escape(prefix)}\s+(\d+)$")

        for key in block.keys():
            if not isinstance(key, str):
                continue

            m = pattern.match(key.strip())
            if m:
                return int(m.group(1))

        return None
