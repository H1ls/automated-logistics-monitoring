from datetime import datetime

from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint
from Navigation_Bot.bots.maps_data_processor import MapsDataProcessor
from Navigation_Bot.bots.yandex_maps_tab import YandexMapsTab
from Navigation_Bot.core.logging import normalize_log_func


class MapsBot:
    SHORT_ROUTE_KM = MapsDataProcessor.SHORT_ROUTE_KM

    def __init__(self, driver_manager, sheets_manager=None, log_func=None):
        self.driver_manager = driver_manager
        self.sheets_manager = sheets_manager
        self.log = normalize_log_func(log_func)
        self.ui = YandexMapsTab(driver_manager, log_func=self.log)
        self.data = MapsDataProcessor()

    def prepare_route_interface(self):
        return self.ui.prepare_route_interface()

    def _handle_short_route(self, car: dict):
        """обработка выгрузки без маршрута"""
        self.log("📦 Короткий маршрут — выгрузка на месте.")
        self.data.apply_short_route_result(car)

    def _build_route_and_get_distance(self, from_coords: str, to_address: str) -> tuple[float, float]:
        """работа с Я.Картами"""
        routes = self.ui.build_route(from_coords, to_address)
        if not routes:
            self.log("❌ Нет маршрутов.")
            # raise ValueError("❌ Нет маршрутов.")
        avg_minutes, avg_distance = self.data.calculate_average_route(routes)
        self.log(f"🛣️ Средний маршрут: {avg_distance} км за {avg_minutes} мин")
        return avg_minutes, avg_distance

    def _finalize_result(self, car: dict, result: dict, avg_distance: float, avg_minutes: float):
        """закрытие маршрута и запись результата"""
        self.ui.close_route()
        self.data.apply_route_result(car, result, avg_distance, avg_minutes)

    def get_route_info(self):
        return self.ui.get_route_info()

    def get_first_route(self):
        return self.ui.get_first_route()

    def _parse_route_item(self, item):
        return self.ui.parse_route_item(item)

    @staticmethod
    def _parse_datetime(date_str, time_str):
        return MapsDataProcessor.parse_datetime(date_str, time_str)

    @staticmethod
    def _duration_to_minutes(time_str):
        return MapsDataProcessor.duration_to_minutes(time_str)

    @staticmethod
    def _calculate_average_route(routes):
        return MapsDataProcessor.calculate_average_route(routes)

    @staticmethod
    def _get_arrival_result_from_datetime(arrival_time, unload_dt):
        return MapsDataProcessor.get_arrival_result(arrival_time, unload_dt)

    # TODO: Переход на Task и домен RoutePoint
    def process_navigation_from_point(self, car: dict, unload_point: RoutePoint):
        if not self.prepare_route_interface():
            return

        from_coords = car.get("коор", "")
        if not from_coords:
            self.log("⚠️ Пропуск: нет координат.")
            return

        address, unload_dt = self._parse_route_point(unload_point)
        if not address or not unload_dt:
            return

        routes = self.ui.build_route(from_coords, address)
        if not routes:
            self.log("❌ Нет маршрутов.")
            return

        avg_minutes, avg_distance = self.data.calculate_average_route(routes)
        self.log(f"🛣️ Средний маршрут: {avg_distance} км за {avg_minutes} мин")

        if avg_distance < self.SHORT_ROUTE_KM:
            self._handle_short_route(car)
            return

        timezone_offset_hours = self.data.calculate_arrival_timezone_offset(routes)
        timezone_text = self.data.format_msk_offset(timezone_offset_hours)

        arrival_time = self.data.calculate_average_arrival(routes, unload_dt)
        if arrival_time:
            suffix = f" ({timezone_text})" if timezone_text else ""
            self.log(f"🕒 ETA Я.Карт в локальном времени выгрузки: {arrival_time:%d.%m.%Y %H:%M}{suffix}")
        else:
            arrival_time = self.data.calculate_arrival_time(avg_distance)
            self.log("⚠️ Я.Карты не отдали ETA, fallback по расстоянию.")

        result = self.data.get_arrival_result(arrival_time, unload_dt, timezone_offset_hours)

        self._finalize_result(car, result, avg_distance, avg_minutes)

    def _parse_route_point(self, point: RoutePoint) -> tuple[str, datetime | None]:
        address, unload_dt, error = self.data.parse_route_point(point)
        if error:
            self.log(error)
        return address, unload_dt
