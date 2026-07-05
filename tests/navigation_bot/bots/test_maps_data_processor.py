from datetime import datetime
from Navigation_Bot.bots.maps_data_processor import MapsDataProcessor
from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint

class TestMapsDataProcessor:

    def test_duration_to_minutes_supports_days_hours_and_minutes(self):
        assert MapsDataProcessor.duration_to_minutes('2 дн. 3 ч 41 мин') == 3101
        assert MapsDataProcessor.duration_to_minutes('~ 1 ч 5 мин') == 65

    def test_calculates_average_route(self):
        routes = [{'duration': '1 ч 10 мин', 'distance': 10.0}, {'duration': '50 мин', 'distance': 20.0}]
        assert MapsDataProcessor.calculate_average_route(routes) == (60, 15)

    def test_parses_yandex_arrival_as_destination_local_time(self):
        arrival = MapsDataProcessor.parse_yandex_arrival('Прибытие 3 июля, в 06:14', year=2026)
        assert arrival == datetime(2026, 7, 3, 6, 14)

    def test_parses_yandex_msk_offset(self):
        assert MapsDataProcessor.parse_yandex_msk_offset('Прибытие 8 июля, в 04:07 (МСК +7)') == 7
        assert MapsDataProcessor.parse_yandex_msk_offset('Прибытие 3 июля, в 10:07 (МСК +0)') == 0
        assert MapsDataProcessor.parse_yandex_msk_offset('Прибытие 3 июля, в 10:07 (МСК -1)') == -1

    def test_calculates_on_time_against_destination_local_deadline(self):
        deadline = datetime(2026, 7, 3, 8, 0)
        arrival = MapsDataProcessor.parse_yandex_arrival('Прибытие 3 июля, в 06:14', year=deadline.year)
        result = MapsDataProcessor.get_arrival_result(arrival, deadline, timezone_offset_hours=7)
        assert result['on_time']
        assert result['buffer_minutes'] == 106
        assert result['time_buffer'] == '1ч 46м'
        assert result['timezone'] == 'МСК +7'
        assert result['timezone_offset_hours'] == 7

    def test_average_arrival_uses_year_nearest_to_deadline(self):
        routes = [{'arrival': 'Прибытие 31 декабря, в 23:30'}]
        deadline = datetime(2027, 1, 1, 1, 0)
        arrival = MapsDataProcessor.calculate_average_arrival(routes, deadline)
        assert arrival == datetime(2026, 12, 31, 23, 30)

    def test_averages_multiple_yandex_routes_from_real_snippets(self):
        routes = [{'duration': '20 ч 47 мин', 'arrival': 'Прибытие 3 июля, в 10:07 (МСК +0)', 'distance': 1740.0}, {'duration': '1 дн. 2 ч 27 мин', 'arrival': 'Прибытие 3 июля, в 15:47 (МСК +0)', 'distance': 1780.0}, {'duration': '22 ч 18 мин', 'arrival': 'Прибытие 3 июля, в 11:38 (МСК +0)', 'distance': 1750.0}]
        deadline = datetime(2026, 7, 3, 16, 0)
        avg_minutes, avg_distance = MapsDataProcessor.calculate_average_route(routes)
        avg_arrival = MapsDataProcessor.calculate_average_arrival(routes, deadline)
        assert avg_minutes == 1391
        assert avg_distance == 1757
        assert avg_arrival == datetime(2026, 7, 3, 12, 31)

    def test_averages_multiple_yandex_arrivals_with_msk_offset(self):
        routes = [{'arrival': 'Прибытие 8 июля, в 04:07 (МСК +7)'}, {'arrival': 'Прибытие 8 июля, в 11:45 (МСК +7)'}]
        deadline = datetime(2026, 7, 8, 12, 0)
        avg_arrival = MapsDataProcessor.calculate_average_arrival(routes, deadline)
        timezone_offset = MapsDataProcessor.calculate_arrival_timezone_offset(routes)
        assert avg_arrival == datetime(2026, 7, 8, 7, 56)
        assert timezone_offset == 7

    def test_parses_route_point_to_address_and_datetime(self):
        point = RoutePoint(kind='unload', sequence=1, address=' Москва ', date='02.07.2026', time='13:45:00')
        address, unload_dt, error = MapsDataProcessor.parse_route_point(point)
        assert address == 'Москва'
        assert unload_dt == datetime(2026, 7, 2, 13, 45)
        assert error is None

    def test_applies_route_result_to_legacy_car_dict(self):
        car = {}
        result = {'время прибытия': '02.07.2026 12:00', 'on_time': True, 'time_buffer': '1ч 0м', 'buffer_minutes': 60}
        MapsDataProcessor.apply_route_result(car, result, avg_distance=42, avg_minutes=50)
        assert car['Маршрут']['расстояние'] == '42 км'
        assert car['Маршрут']['длительность'] == '50 мин'
        assert car['Маршрут']['успеет']

    def test_applies_timezone_to_legacy_car_dict_when_present(self):
        car = {}
        result = {'время прибытия': '08.07.2026 07:56', 'on_time': True, 'time_buffer': '4ч 4м', 'buffer_minutes': 244, 'timezone': 'МСК +7', 'timezone_offset_hours': 7}
        MapsDataProcessor.apply_route_result(car, result, avg_distance=0, avg_minutes=0)
        assert car['Маршрут']['timezone'] == 'МСК +7'
        assert car['Маршрут']['timezone_offset_hours'] == 7
