import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from Navigation_Bot.core.json_store import JsonStore
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.logging import normalize_log_func


class YandexMapsTab:
    def __init__(self, driver_manager, log_func=None):
        self.driver_manager = driver_manager
        self.log = normalize_log_func(log_func)
        self.selectors = JsonStore.get_selectors("yandex_selectors", CONFIG_JSON)

    def by(self, key: str):
        val = self.selectors.get(key)
        if not val:
            raise ValueError(f"Селектор для '{key}' не найден в конфиге.")
        if val.startswith("/"):
            return By.XPATH, val
        if val.startswith("."):
            return By.CSS_SELECTOR, val
        return By.CLASS_NAME, val

    def try_click(self, key: str, label: str = "", timeout=3) -> bool:
        try:
            self.driver_manager.click(self.by(key), timeout=timeout)
            time.sleep(0.3)
            return True
        except Exception:
            self.log(f"⚠️ Не удалось нажать '{label or key}'")
            return False

    def prepare_route_interface(self) -> bool:
        if self.try_click("route_button", "Маршруты"):
            return True
        self.try_click("close_route", "Закрыть маршрут")
        return self.try_click("route_button", "Маршруты")

    def close_route(self) -> None:
        try:
            self.driver_manager.click(self.by("close_route"))
        except Exception:
            pass

    def build_route(self, from_coords: str, to_address: str) -> list[dict]:
        self.enter_from_coordinates(from_coords)
        self.enter_to_address(to_address)
        return self.get_route_info()

    def enter_to_address(self, address: str) -> None:
        self.log(f"📥 Ввод точки назначения: {address}")
        to_input = self.driver_manager.find(self.by("to_input"))
        self.driver_manager.execute_js("arguments[0].focus();", to_input)
        to_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, address)
        to_input.send_keys(Keys.ENTER)
        time.sleep(0.5)

        try:
            scroll_el = self.driver_manager.driver.find_element(By.CSS_SELECTOR, "div.scroll._width_narrow")
            class_value = scroll_el.get_attribute("class")

            time.sleep(0.35)
            if "_disabled" in class_value:
                to_input.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.1)
                to_input.send_keys(Keys.ENTER)
        except Exception as e:
            self.log(f"⚠️ Не удалось проверить состояние scroll-контейнера: {e}")

    def enter_from_coordinates(self, coord: str) -> None:
        self.log(f"🚚 Ввод координат машины: {coord}")
        try:
            from_input = self.driver_manager.find(self.by("from_input"), timeout=10)
            from_input.click()

            self.driver_manager.execute_js("arguments[0].focus();", from_input)
            from_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            from_input.send_keys(coord)
            from_input.send_keys(Keys.ENTER)
            time.sleep(1)
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка ввода в 'Откуда': {msg}")

    def get_route_info(self) -> list[dict]:
        try:
            for _ in range(10):
                items = self.driver_manager.find_all(self.by("route_item"), timeout=10)
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
                parsed = self.parse_route_item(item)
                if parsed:
                    all_routes.append(parsed)

            return all_routes
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка получения маршрутов: {msg}")
            return []

    def get_first_route(self) -> dict | None:
        try:
            items = self.driver_manager.find_all(self.by("route_item"), timeout=10)
            if not items:
                return None

            first_auto = None
            for el in items:
                try:
                    if "_type_auto" in (el.get_attribute("class") or ""):
                        first_auto = el
                        break
                except Exception:
                    continue

            item = first_auto or items[0]
            if "_type_auto" not in (item.get_attribute("class") or ""):
                return None

            return self.parse_route_item(item)
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка при получении первого маршрута: {msg}")
            return None

    def parse_route_item(self, item) -> dict | None:
        try:
            time_el = item.find_element(*self.by("route_duration"))
            dist_el = item.find_element(*self.by("route_distance"))
            arrival_text = ""
            try:
                arrival_el = item.find_element(By.CLASS_NAME, "auto-route-snippet-view__arrival")
                arrival_text = arrival_el.text.strip().replace("\xa0", " ")
            except Exception:
                pass

            duration = time_el.text.strip().replace("\xa0", " ")
            dist_text = dist_el.text.strip().replace("\xa0", "").replace(" ", "").replace(",", ".").replace("км", "")

            try:
                distance = float(dist_text)
            except ValueError:
                if "м" in dist_text:
                    self.log(f"📏 Короткий маршрут (< 1 км): {dist_text}")
                    return {"duration": "0", "distance": 0.0}
                raise

            return {"duration": duration, "distance": distance, "arrival": arrival_text}
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка разбора маршрута: {msg}")
            return None
