from config.requirements import *


class MapsBot:
    def __init__(self, web_driver_manager, sheets_manager):
        self.web_driver_manager = web_driver_manager
        self.sheets_manager = sheets_manager

    def enter_route(self, start_coords, destination_address):
        """Заполняет поле 'Откуда' и 'Куда' на карте"""
        try:
            driver = self.web_driver_manager.driver
            driver.switch_to.window(driver.window_handles[0])

            self._fill_input("//input[@placeholder='Откуда']", start_coords)
            self._fill_input("//input[@placeholder='Куда']", destination_address)

            self.web_driver_manager("//div[contains(@class, 'route-snippet-view') and contains(@class, '_type_auto')]")
        except Exception as e:
            print(f"Ошибка в 'enter_route': {e}")

    def _clean_input(self):
        def clear_element(locator):
            element = self.web_driver_manager.web_driver_wait(locator)
            element.send_keys(Keys.CONTROL, "a", Keys.BACKSPACE)
            WebDriverWait(self.web_driver_manager.driver, 3).until(lambda d: element.get_attribute("value") == "")

        clear_element("//input[@placeholder='Откуда']")
        clear_element("//input[@placeholder='Куда']")

    def _fill_input(self, xpath, value):
        """Заполняет поле ввода"""
        element = self.web_driver_manager.web_driver_wait(xpath)
        element.clear()
        element.send_keys(value)
        element.send_keys(Keys.ENTER)
        # Удалить ?
        WebDriverWait(self.web_driver_manager.driver, 3).until(lambda d: element.get_attribute("value") == value)

    def get_route_info(self):
        try:
            self.web_driver_manager.web_driver_wait(
                "//div[contains(@class, 'route-snippet-view') and contains(@class, '_type_auto')]")

            elements = self.web_driver_manager.driver.find_elements(
                By.XPATH,
                "//div[contains(@class, 'route-snippet-view') and contains(@class, '_type_auto') and @aria-hidden='false']")
            if not elements:
                print("Ошибка: Маршруты не найдены. Возможно, не загрузились.")
                return []

            routes = []
            for element in elements:
                try:
                    duration = element.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'auto-route-snippet-view__route-duration')]").text.strip()
                    distance = element.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'auto-route-snippet-view__route-subtitle')]").text.strip()
                    routes.append((duration, distance))
                except NoSuchElementException:
                    print("Маршрут найден, но не удалось извлечь данные.")

            if not routes:
                print("Ошибка: Не удалось извлечь данные о маршрутах.")
            else:
                print(f"Найдено {len(routes)} маршрутов: {routes}")
            self._clean_input()
            return routes

        except TimeoutException:
            print("Ошибка: Тайм-аут ожидания маршрутов.")
            return []
        except Exception as e:
            print(f"Ошибка в 'get_route_info': {e}")
            return []

    def calculate_arrival_time(self, avg_time, unload_datetime):
        """Рассчитывает время прибытия и проверяет, успевает ли машина на выгрузку"""
        arrival_time = datetime.now() + timedelta(minutes=avg_time)
        time_buffer = (unload_datetime - arrival_time).total_seconds() / 60  # Запас времени в минутах
        buffer_hours = int(time_buffer // 60)
        buffer_minutes = int(time_buffer % 60)
        return {
            "время прибытия": arrival_time.strftime("%d.%m.%Y %H:%M"),
            "время разгрузки": unload_datetime.strftime("%d.%m.%Y %H:%M"),
            "on_time": arrival_time <= unload_datetime,
            "time_buffer": f"{buffer_hours}:{buffer_minutes:02d}"  # Запас времени в формате часы:минуты
        }

    def process_navigation_from_json(self, input_filepath):
        """Обрабатывает JSON-файл с маршрутами"""
        try:
            with open(input_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            for car in data:
                start_coords = car.get("коор")
                unload_info = car.get("Выгрузка", [{}])[0]
                destination_address = unload_info.get("Выгрузка 1")
                unload_datetime = self._parse_datetime(unload_info.get("Дата 1"), unload_info.get("Время 1"))

                if not (start_coords and destination_address and unload_datetime):
                    print(f"Пропуск машины {car.get('ТС')}: некорректные данные")
                    continue

                self.enter_route(start_coords, destination_address)
                routes = self.get_route_info()

                if not routes:
                    print(f"Нет маршрутов для {car.get('ТС')}")
                    continue

                avg_time, avg_distance = self._calculate_average_route(routes)
                arrival_result = self.calculate_arrival_time(avg_time, unload_datetime)

                car["Маршрут"] = {
                    "Среднее время (мин)": avg_time,
                    "Среднее расстояние (км)": avg_distance,
                    "Расчет прибытия": arrival_result
                }

                if int(arrival_result["time_buffer"].split(":")[0]) < 0:
                    print(f"Внимание! Маленький запас времени у {car.get('ТС')} ({arrival_result['time_buffer']})")

                print(f"Обработана {car.get('ТС')}: {car['Маршрут']}")

            self.sheets_manager.save_json(data, input_filepath)
        except Exception as e:
            print(f"Ошибка при обработке JSON: {e}")

    @staticmethod
    def _parse_datetime(date_str, time_str):
        """Парсит дату и время в объект datetime"""
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _calculate_average_route(routes):
        """Вычисляет среднее расстояние и время"""
        times, distances = zip(*[(MapsBot._convert_time(t), MapsBot._convert_distance(d)) for t, d in routes])
        return round(sum(times) / len(times)), round(sum(distances) / len(distances))

    @staticmethod
    def _convert_time(time_str):
        """Конвертирует '5 ч 30 мин' в минуты"""
        hours = sum(map(int, re.findall(r'(\d+)\s*ч', time_str)))
        minutes = sum(map(int, re.findall(r'(\d+)\s*мин', time_str)))
        return hours * 60 + minutes

    @staticmethod
    def _convert_distance(distance_str):
        """Конвертирует '490 км' в км"""
        return int(re.search(r'(\d+)', distance_str).group(1)) if distance_str else 0

    @staticmethod
    def calculate_time(distance):
        """Рассчитывает время с учётом прогрессии"""
        if distance <= 100:
            return 1  # 100 км - 1 час
        base_time = 1  # Начальная точка (100 км = 1 ч)
        factor = 0.5  # Увеличение времени на каждом шаге
        exponent = math.log2(distance / 100)
        return round(base_time + factor * exponent, 2)
