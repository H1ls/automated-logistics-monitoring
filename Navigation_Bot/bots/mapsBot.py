import re
import time
from datetime import datetime, timedelta
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.jSONManager import JSONManager

"""TODO 1.MapsBot - запускает вспомогательные классы 
        2.Вынести ввод и клики в MapsUIHelper
        3.Вынести парсинг маршрутов в отдельный класс
        4.Вынести address+datetime обработку"""


class MapsBot:
    def __init__(self, driver_manager, sheets_manager=None, log_func=None):
        self.driver_manager = driver_manager
        self.sheets_manager = sheets_manager
        self.log = log_func or print
        self._load_selectors()

    def _load_selectors(self):
        self.selectors = JSONManager.get_selectors("yandex_selectors", CONFIG_JSON)
        # self.log("✅ Селекторы Яндекс.Карт загружены.")

    def _by(self, key):
        val = self.selectors.get(key)
        if not val:
            raise ValueError(f"Селектор для '{key}' не найден в конфиге.")
        if val.startswith("/"):
            return (By.XPATH, val)
        elif val.startswith("."):
            return (By.CSS_SELECTOR, val)
        else:
            return (By.CLASS_NAME, val)

    def _try_click(self, key: str, label: str = "", timeout=3) -> bool:
        try:
            locator = self._by(key)
            self.driver_manager.click(locator, timeout=timeout)
            # if label:
            #     pass
                # self.log(f"✅ Нажата кнопка '{label}'")

            time.sleep(0.3)
            return True
        except Exception as e:
            self.log(f"⚠️ Не удалось нажать '{label or key}': {e}")
            return False

    def prepare_route_interface(self):
        if self._try_click("route_button", "Маршруты"):
            return True
        self._try_click("close_route", "Закрыть маршрут")
        return self._try_click("route_button", "Маршруты")

    def process_navigation_from_json(self, car: dict, unload_point: dict):
        if not self.prepare_route_interface():
            return

        from_coords = car.get("коор", "")
        if not from_coords:
            self.log("⚠️ Пропуск: нет координат.")
            return

        address, unload_dt = self._parse_unload_block(unload_point)
        if not address or not unload_dt:
            return

        avg_minutes, avg_distance = self._build_route_and_get_distance(from_coords, address)

        if avg_distance < 1:
            self._handle_short_route(car)
            return

        arrival_time = datetime.now() + timedelta(hours=avg_distance / 66)
        result = self._get_arrival_result_from_datetime(arrival_time, unload_dt)

        self._finalize_result(car, result, avg_distance, avg_minutes)

    def _parse_unload_block(self, unload_point: dict) -> tuple[str, datetime | None]:
        for key in unload_point:
            if key.startswith("Выгрузка "):
                idx = key.split(" ")[1]
                break
        else:
            idx = "1"

        address = unload_point.get(f"Выгрузка {idx}", "").strip()
        date_str = unload_point.get(f"Дата {idx}", "").strip()
        time_str = unload_point.get(f"Время {idx}", "").strip()

        if not address or not date_str or not time_str:
            self.log("⚠️ Пропуск: неполные данные о выгрузке.")
            return "", None

        unload_dt = self._parse_datetime(date_str, time_str)
        return address, unload_dt

    def _handle_short_route(self, car: dict):
        """обработка выгрузки без маршрута"""
        self.log("📦 Короткий маршрут — выгрузка на месте.")
        car["гео"] = "у выгрузки"

        # Убрать, кроме выгрузки данные не нужны
        car["коор"] = ""
        car["скорость"] = 0
        arrival = datetime.now().strftime("%d.%m.%Y %H:%M")
        car["Маршрут"] = {
            "расстояние": "0.0 км",
            "длительность": "0 мин",
            "время прибытия": arrival,
            "успеет": True,
            "time_buffer": "—"
        }

    def _build_route_and_get_distance(self, from_coords: str, to_address: str) -> tuple[float, float]:
        """работа с Я.Картами"""
        self._enter_from_coordinates(from_coords)
        self._enter_to_address(to_address)

        self.driver_manager.find_all(self._by("route_item"), timeout=10)

        routes = self.get_route_info()
        if not routes:
            raise ValueError("❌ Нет маршрутов.")
        avg_minutes, avg_distance = self._calculate_average_route(routes)
        self.log(f"🛣️ Средний маршрут: {avg_distance} км за {avg_minutes} мин")
        return avg_minutes, avg_distance

    def _finalize_result(self, car: dict, result: dict, avg_distance: float, avg_minutes: float):
        """закрытие маршрута и запись результата"""
        try:
            self.driver_manager.click(self._by("close_route"))
        except Exception:
            pass

        car["Маршрут"] = {
            "расстояние": f"{avg_distance} км",
            "длительность": f"{avg_minutes} мин",
            "время прибытия": result["время прибытия"],
            "успеет": result["on_time"],
            "time_buffer": result["time_buffer"],
            "buffer_minutes": result["buffer_minutes"]
        }

    def _enter_to_address(self, address):
        self.log(f"📥 Ввод точки назначения: {address}")
        to_input = self.driver_manager.find(self._by("to_input"))
        self.driver_manager.execute_js("arguments[0].focus();", to_input)
        to_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, address)
        to_input.send_keys(Keys.ENTER)
        time.sleep(0.5)

        # появился ли класс "_disabled" у scroll-контейнера
        try:
            scroll_el = self.driver_manager.driver.find_element(By.CSS_SELECTOR, "div.scroll._width_narrow")
            class_value = scroll_el.get_attribute("class")

            if "_disabled" in class_value:
                # открылся список подсказок
                # self.log("🟡 Обнаружен список подсказок - выбираю первый элемент.")
                to_input.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.1)
                to_input.send_keys(Keys.ENTER)

            # ?
            else:
                pass
                # self.log("🟢 Список подсказок НЕ появился - адрес принят сразу.")

        except Exception as e:
            self.log(f"⚠️ Не удалось проверить состояние scroll-контейнера: {e}")

    def _enter_from_coordinates(self, coord):
        self.log(f"🚚 Ввод координат машины: {coord}")
        try:
            locator = self._by("from_input")
            from_input = self.driver_manager.find(locator, timeout=10)
            from_input.click()

            self.driver_manager.execute_js("arguments[0].focus();", from_input)
            from_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            from_input.send_keys(coord)
            from_input.send_keys(Keys.ENTER)
            # self.log("✅ Координаты 'Откуда' введены.")

        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка ввода в 'Откуда': {msg}")

    def get_route_info(self):
        # self.log("⌛ Получение всех маршрутов...")
        try:
            for _ in range(10):
                items = self.driver_manager.find_all(self._by("route_item"), timeout=10)
                filtered = [el for el in items if "_type_auto" in el.get_attribute("class")]
                if filtered:
                    break
                time.sleep(1)
            else:
                self.log("❗ Маршруты не найдены, fallback...")
                route = self.get_first_route()
                return [route] if route else []

            all_routes = []
            for item in filtered:
                parsed = self._parse_route_item(item)
                if parsed:
                    all_routes.append(parsed)

            # self.log(f"📦 Найдено маршрутов: {len(all_routes)}\n {all_routes}")
            return all_routes

        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка получения маршрутов: {msg}")
            return []

    def get_first_route(self):
        try:
            item = self.driver_manager.find_all(self._by("route_item"))

            if "_type_auto" not in item.get_attribute("class"):
                return None
            return self._parse_route_item(item)
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка при получении первого маршрута: {msg}")
            return None

    def _parse_route_item(self, item):
        try:
            time_el = item.find_element(*self._by("route_duration"))
            dist_el = item.find_element(*self._by("route_distance"))

            duration = time_el.text.strip().replace("\xa0", " ")
            dist_text = dist_el.text.strip().replace("\xa0", "").replace(" ", "").replace(",", ".").replace("км", "")

            try:
                distance = float(dist_text)
            except ValueError:
                # Пробуем отфильтровать метры: "800м", "0м" и т.п.
                if "м" in dist_text:
                    self.log(f"📏 Короткий маршрут (< 1 км): {dist_text}")
                    return {"duration": "0",
                            "distance": 0.0}
                raise

            return {
                "duration": duration,
                "distance": distance
            }

        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка разбора маршрута: {msg}")
            return None

    @staticmethod
    def _parse_datetime(date_str, time_str):
        try:
            # пробуем с секундами
            return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
        except ValueError:
            try:
                # пробуем без секунд
                return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            except Exception as e:
                # print(f"❗ Не удалось распарсить дату/время: '{date_str}' '{time_str}' → {e}")
                return None

    @staticmethod
    def _duration_to_minutes(time_str):
        """Преобразует '2 дн. 3 ч 41 мин' в минуты (int)."""
        try:
            time_str = time_str.strip().lower().replace("~", "")
            total_min = 0

            pattern = r"(?:(\d+)\s*дн\.)?\s*(?:(\d+)\s*ч)?\s*(?:(\d+)\s*мин)?"
            match = re.search(pattern, time_str)
            if not match:
                raise ValueError("Неверный формат")

            days = int(match.group(1)) if match.group(1) else 0
            hours = int(match.group(2)) if match.group(2) else 0
            minutes = int(match.group(3)) if match.group(3) else 0

            total_min = days * 1440 + hours * 60 + minutes
            return total_min

        except Exception as e:
            raise ValueError(f"Ошибка разбора времени: {time_str} → {e}")

    @staticmethod
    def _calculate_average_route(routes):
        times = [MapsBot._duration_to_minutes(r["duration"]) for r in routes]
        distances = [r["distance"] for r in routes]
        return round(sum(times) / len(times)), round(sum(distances) / len(distances))

    @staticmethod
    def _get_arrival_result_from_datetime(arrival_time, unload_dt):
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
            "buffer_minutes": total_minutes
        }
