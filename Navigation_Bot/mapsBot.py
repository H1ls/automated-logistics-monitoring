import time
import json
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class MapsBot:
    def __init__(self, driver, sheets_manager=None, log_func=None):
        self.driver = driver
        self.sheets_manager = sheets_manager
        self.log = log_func or print
        self.settings = self._load_settings()

    def _load_settings(self):
        try:
            with open("config/mapsbot_default_settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
            try:
                with open("config/mapsbot_default_settings.json", "r", encoding="utf-8") as f:
                    settings.update(json.load(f))
                    self.log("⚙️ Используются пользовательские настройки MapsBot")
            except FileNotFoundError:
                self.log("ℹ️ Используются стандартные настройки MapsBot")
            return settings
        except Exception as e:
            self.log(f"❌ Ошибка загрузки настроек MapsBot: {e}")
            return {
                "selectors": {
                    "route_container_class": "auto-route-snippet-view",
                    "duration_class": "auto-route-snippet-view__duration",
                    "distance_class": "auto-route-snippet-view__distance"
                },
                "xpaths": {
                    "duration_xpath": ".//div[contains(@class, '__duration')]",
                    "distance_xpath": ".//div[contains(@class, '__distance')]"
                },
                "delays": {
                    "initial_render_wait_sec": 2,
                    "route_attempts": 10,
                    "per_attempt_wait_sec": 1
                },
                "fallback_enabled": True,
                "version": "embedded"}

    def web_driver_wait(self, xpath, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )

    def click_route_button(self):
        self.log("📍 Нажатие кнопки 'Маршруты'...")
        try:
            route_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@class, 'button _view_search _size_medium _link')]"))
            )
            route_button.click()
            time.sleep(1)
        except:
            self.log("❗ Кнопка маршрута не найдена или уже нажата.")

    def enter_route(self, coord, address):
        self.log(f"📤 Ввод маршрута:Откуда → {coord}Куда   → {address}")
        try:
            from_input = self.web_driver_wait("//input[@placeholder='Откуда']")
            from_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            time.sleep(0.5)
            from_input.send_keys(coord)
            time.sleep(1)
            from_input.send_keys(Keys.ENTER)
            time.sleep(2)

            to_input = self.web_driver_wait("//input[@placeholder='Куда']")
            to_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            time.sleep(0.5)
            to_input.send_keys(address)
            time.sleep(1)
            to_input.send_keys(Keys.ENTER)
            time.sleep(2)

        except Exception as e:
            self.log(f"❌ Ошибка при вводе маршрута: {e}")

    def get_route_info(self):
        self.log("⌛ Ожидание отрисовки маршрутов (2 сек)...")
        time.sleep(self.settings["delays"]["initial_render_wait_sec"])

        self.log("⌛ Получение всех маршрутов...")
        try:
            routes = []
            for attempt in range(self.settings["delays"]["route_attempts"]):
                self.log(f"🔄 Попытка {attempt + 1}: поиск маршрутов...")
                items = self.driver.find_elements(By.CLASS_NAME, self.settings["selectors"]["route_container_class"])
                if items:
                    self.log(f"✅ Найдено маршрутов: {len(items)}")
                    for item in items:
                        parsed = self._parse_route_item(item)
                        if parsed:
                            routes.append(parsed)
                    break
                time.sleep(self.settings["delays"]["per_attempt_wait_sec"])

            if not routes and self.settings.get("fallback_enabled", True):
                self.log("❗ Список маршрутов не найден, пробуем напрямую...")
                fallback = self.get_first_route()
                return [fallback] if fallback else []

            return routes

        except Exception as e:
            self.log(f"❌ Ошибка получения маршрутов: {e}")
            return []

    def _parse_route_item(self, item):
        try:
            # Основной способ через CSS
            try:
                time_el = item.find_element(By.CLASS_NAME, self.settings["selectors"]["duration_class"])
                dist_el = item.find_element(By.CLASS_NAME, self.settings["selectors"]["distance_class"])
            except:
                # Fallback через XPath
                time_el = item.find_element(By.XPATH, self.settings["xpaths"]["duration_xpath"])
                dist_el = item.find_element(By.XPATH, self.settings["xpaths"]["distance_xpath"])

            duration = time_el.text.strip().replace("\xa0", " ").replace(" мин", "").replace(" ч ", ":")
            if ":" not in duration:
                duration = f"0:{duration}"

            distance = dist_el.text.strip().replace("\xa0", " ").split()[0].replace(",", ".")
            self.log(f"duration:{duration}, distance: {float(distance)}")
            return {"duration": duration, "distance": float(distance)}

        except Exception as e:
            self.log(f"⚠️ Не удалось распарсить маршрут: {e}")
            return None

    def get_first_route(self):
        self.log("📍 Получение первого маршрута напрямую...")
        try:
            item = self.driver.find_element(By.CLASS_NAME, self.settings["selectors"]["route_container_class"])
            return self._parse_route_item(item)
        except Exception as e:
            self.log(f"❌ Не удалось получить первый маршрут: {e}")
            return None

    def process_navigation_from_json(self, car):
        try:
            coord = car.get("коор", "")
            unload_blocks = car.get("Выгрузка", [])
            if not coord or not unload_blocks:
                self.log("❌ Нет координат или выгрузки — маршрут пропущен.")
                return

            address = unload_blocks[0].get("Выгрузка 1", "")
            date = unload_blocks[0].get("Дата 1", "")
            time_str = unload_blocks[0].get("Время 1", "")
            unload_dt = self._parse_datetime(date, time_str)

            self.click_route_button()
            self.enter_route(coord, address)
            routes = self.get_route_info()

            if not routes:
                self.log("❌ Данные маршрута не получены.")
                return

            avg_min, avg_km = self._calculate_average_route(routes)
            arrival_result = self.calculate_arrival_time_from_minutes(avg_min, unload_dt)

            car["Маршрут"] = {
                "Среднее время (мин)": avg_min,
                "Среднее расстояние (км)": avg_km,
                "Расчет прибытия": arrival_result
            }

            self.log(f"✅ Расчёт завершён для {car.get('ТС')}:\n {arrival_result}")

        except Exception as e:
            self.log(f"❌ Ошибка в process_navigation_from_json: {e}")

    @staticmethod
    def _parse_datetime(date_str, time_str):
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _duration_to_minutes(time_str):
        h, m = map(int, time_str.split(":"))
        return h * 60 + m

    @staticmethod
    def _calculate_average_route(routes):
        times = [MapsBot._duration_to_minutes(r["duration"]) for r in routes]
        distances = [r["distance"] for r in routes]
        return round(sum(times) / len(times)), round(sum(distances) / len(distances))

    @staticmethod
    def calculate_arrival_time_from_minutes(avg_minutes, unload_datetime):
        arrival_time = datetime.now() + timedelta(minutes=avg_minutes)
        if unload_datetime:
            buffer = unload_datetime - arrival_time
            total_minutes = int(buffer.total_seconds() // 60)
        else:
            total_minutes = 0

        buf_hours = total_minutes // 60
        buf_minutes = total_minutes % 60

        return {
            "время прибытия": arrival_time.strftime("%d.%m.%Y %H:%M"),
            "время разгрузки": unload_datetime.strftime("%d.%m.%Y %H:%M") if unload_datetime else "Не указано",
            "on_time": unload_datetime and arrival_time <= unload_datetime,
            "time_buffer": f"{buf_hours}:{buf_minutes:02d}"
        }
