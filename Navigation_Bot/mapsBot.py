import time
import pyperclip
import json
from datetime import datetime, timedelta
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from Navigation_Bot.jSONManager import JSONManager


class MapsBot:
    def __init__(self, driver, sheets_manager=None, log_func=None):
        self.driver = driver
        self.sheets_manager = sheets_manager
        self.log = log_func or print
        self._load_selectors()

    def _load_selectors(self):
        self.selectors = JSONManager.get_selectors("yandex_selectors")
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

    def web_driver_wait(self, locator, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located(locator)
        )

    def prepare_route_interface(self):
        sel = self.selectors

        try:
            # 1. Закрыть маршрут (если открыт)
            close_selector = sel.get("close_route", "")
            if close_selector:
                try:
                    close_locator = self._by("close_route")

                    btn = self.web_driver_wait(close_locator, timeout=3)
                    btn.click()
                    self.log("❌ Закрыт предыдущий маршрут.")
                    time.sleep(0.3)
                except Exception:
                    pass  # кнопки закрытия может не быть — не критично

            # 2. Нажать "Маршруты"
            route_selector = sel.get("route_button", "")
            if route_selector:
                try:
                    route_locator = self._by("route_button")

                    btn = self.web_driver_wait(route_locator, timeout=5)
                    btn.click()
                    self.log("📍 Нажата кнопка 'Маршруты'.")
                    time.sleep(0.3)
                    return True
                except Exception:
                    self.log("⚠️ Кнопка 'Маршруты' не найдена.")
                    return False

            return False

        except Exception as e:
            self.log(f"❌ Ошибка подготовки маршрута: {str(e).splitlines()[0]}")
            return False

    def process_navigation_from_json(self, car: dict):
        try:
            if not self.prepare_route_interface():
                return

            from_coords = car.get("коор", "")
            if not from_coords:
                self.log("⚠️ Пропуск: нет координат.")
                return

            # --- Найти первую валидную выгрузку с адресом и датой/временем ---
            unloads = car.get("Выгрузка", [])
            selected_address = None
            unload_datetime = None

            for i, unload in enumerate(unloads):
                key = f"Выгрузка {i + 1}"
                date_str = unload.get(f"Дата {i + 1}", "").strip()
                time_str = unload.get(f"Время {i + 1}", "").strip()
                address = unload.get(key, "").strip()

                if address and date_str and time_str:
                    selected_address = address
                    unload_datetime = self._parse_datetime(date_str, time_str)
                    break

            if not selected_address or not unload_datetime:
                self.log("⚠️ Пропуск: нет полной информации о выгрузке.")
                return

            # --- Ввод координат и адреса ---
            self._enter_from_coordinates(from_coords)
            self._enter_to_address(selected_address)

            # --- Получение маршрутов ---
            routes = self.get_route_info()
            if not routes:
                self.log("❌ Нет маршрутов.")
                return

            avg_minutes, avg_distance = self._calculate_average_route(routes)
            self.log(f"🛣️ Средний маршрут: {avg_distance} км за {avg_minutes} мин")

            # --- Сравнение прибытия с датой/временем выгрузки ---
            result = self._get_arrival_result(avg_minutes, unload_datetime)
            self.log(
                f"⏱️ Прибытие: {result['время прибытия']}, "
                f"Выгрузка: {result['время разгрузки']} → "
                f"{'✅ успевает' if result['on_time'] else '❌ опаздывает'}"
            )

            # --- Закрытие маршрута ---
            try:
                close_btn = self.web_driver_wait(self._by("close_route"), timeout=5)
                close_btn.click()
                time.sleep(0.3)
                print("Закрытие маршрута")
            except Exception:
                print("Не получилось - Закрытие маршрута")

            # --- Сохранение результата ---
            car["Маршрут"] = {
                "расстояние": f"{avg_distance} км",
                "длительность": f"{avg_minutes} мин",
                "время прибытия": result["время прибытия"],
                "успеет": result["on_time"],
                "time_buffer": result["time_buffer"]
            }

        except Exception as e:
            self.log(f"❌ Ошибка маршрута: {str(e).splitlines()[0]}")

    def _enter_to_address(self, address):
        self.log(f"📥 Ввод точки назначения: {address}")
        to_input = self.web_driver_wait(self._by("to_input"))
        to_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, address, Keys.ENTER)
        time.sleep(1)

    def _enter_from_coordinates(self, coord):
        # self.log(f"🚚 Ввод координат машины: {coord}")
        try:
            from_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(self._by("from_input"))
            )

            self.driver.execute_script("arguments[0].focus();", from_input)
            time.sleep(0.5)
            from_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            from_input.send_keys(coord, Keys.ENTER)
            time.sleep(1)
            # self.log("✅ Координаты 'Откуда' введены.")
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка ввода в 'Откуда': {msg}")

    def get_route_info(self):
        self.log("⌛ Получение всех маршрутов...")
        try:
            for _ in range(10):
                items = self.driver.find_elements(*self._by("route_item"))
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

            self.log(f"📦 Найдено маршрутов: {len(all_routes)}\n {all_routes}")
            return all_routes

        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка получения маршрутов: {msg}")
            return []

    def get_first_route(self):
        try:
            item = self.driver.find_element(*self._by("route_item"))
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
            distance = float(dist_text)

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
                print(f"❗ Не удалось распарсить дату/время: '{date_str}' '{time_str}' → {e}")
                return None

    @staticmethod
    def _duration_to_minutes(time_str):
        """Преобразует '2 дн. 3 ч 41 мин' в минуты (int)."""
        try:
            import re
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

    def _get_arrival_result(self, avg_minutes, unload_dt):
        arrival_time = datetime.now() + timedelta(minutes=avg_minutes)

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
            "time_buffer": f"{buf_hours}:{buf_minutes:02d}",
            "buffer_minutes": total_minutes
        }
