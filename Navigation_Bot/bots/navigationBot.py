import re
import time
import pyperclip

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from unicodedata import digit

from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import CONFIG_JSON


class NavigationBot:
    # --- настройки поведения ---
    STALE_GPS_SECONDS = 3600  # 1 час
    DEFAULT_TIMEOUT = 15
    ADDRESS_READY_TIMEOUT = 12
    CLIPBOARD_TIMEOUT = 2.5

    REQUIRED_KEYS = [
        "search_input_xpath",
        "unit_block_xpath",
        "address_selector",
        "copy_button_selector",
        "speed_selector",
        "gps_sats_xpath",
        "monitoring",
    ]

    def __init__(self, driver, log_func=None):
        self.driver = driver
        self.log = log_func or print
        self.json_manager = JSONManager(CONFIG_JSON)

        self.selectors = self.load_selectors()
        self.validate_selectors()

    # --- A. Init / config
    def load_selectors(self) -> dict:
        try:
            return JSONManager.get_selectors("wialon_selectors", CONFIG_JSON)
        except Exception as e:
            self.log(f"❌ Ошибка загрузки селекторов: {self._short_err(e)}")
            raise

    def validate_selectors(self) -> None:
        for key in self.REQUIRED_KEYS:
            if key not in self.selectors or not self.selectors[key]:
                raise ValueError(f"⛔ Отсутствует селектор '{key}' в конфиге")

    # --- B. Selenium helpers
    def _wait_visible_xpath(self, xpath: str, timeout: int = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(EC.visibility_of_element_located((By.XPATH, xpath)))

    def _wait_present_css(self, css: str, timeout: int = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

    def _safe_find_css(self, css: str):
        try:
            return self.driver.find_element(By.CSS_SELECTOR, css)
        except Exception:
            return None

    def _hover(self, element) -> None:
        ActionChains(self.driver).move_to_element(element).perform()

    def _short_err(self, e: Exception) -> str:
        # return str(e).splitlines()[0] if e else "unknow error"
        return str(e) if e else "unknow error"

    # --- C. Page actions
    def _focus_search_input(self):
        xpath = self.selectors["search_input_xpath"]
        try:
            return self._wait_visible_xpath(xpath, timeout=8)
        except Exception:
            # пробуем открыть мониторинг ещё раз и повторить
            self._ensure_monitoring_open()
            return self._wait_visible_xpath(xpath, timeout=20)

    def _clear_search(self) -> None:
        try:
            input_element = self._focus_search_input()
            input_element.click()
            input_element.send_keys(Keys.CONTROL + "a")
            input_element.send_keys(Keys.BACKSPACE)
            self.driver.execute_script("document.activeElement.blur();")
        except Exception as e:
            self.log(f"❌ Ошибка в _clear_search: {self._short_err(e)}")

    def _type_in_search(self, text: str) -> bool:
        try:
            search_input = self._focus_search_input()
            search_input.click()
            search_input.send_keys(text)
            # el = self.selectors["move_to_element"]
            # ActionChains(self.driver).move_to_element(el).perform()
            self.driver.execute_script("document.activeElement.blur();")
            return True
        except Exception as e:
            self.log(
                f"❌ Не удалось ввести текст в поиск '{text}': {self._short_err(e)} -> NavigationBot._type_in_search")
            # car_data["_новые_координаты"] = False
            # car_data["коор"] = None
            # car_data["гео"] = None
            return False

    def _find_car_element(self, car_id) -> object | None:
        try:
            xpath_tpl = self.selectors["unit_block_xpath"]
            xpath = xpath_tpl.replace("{car_id}", str(car_id))
            return self._wait_visible_xpath(xpath, timeout=112)
        except Exception as e:
            self.log(f"❌ Машина с ID {car_id} не найдена: {self._short_err(e)} -> NavigationBot._find_car_element")
            return None

    def _ensure_monitoring_open(self) -> None:
        try:
            btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@id='hb_mi_monitoring']")))
            btn.click()
            self.log("📡 Открыт 'Мониторинг'.")
        except Exception:
            pass

    def _ensure_on_wialon_tab(self) -> bool:
        try:
            url = (self.driver.current_url or "").lower()
            title = (self.driver.title or "").lower()
            if ("wialon" in url) or ("rtmglonass" in url) or ("wialon" in title):
                return True

            # если сейчас не Wialon — попробуем найти вкладку среди всех
            for h in self.driver.window_handles:
                self.driver.switch_to.window(h)
                url = (self.driver.current_url or "").lower()
                title = (self.driver.title or "").lower()
                if ("wialon" in url) or ("rtmglonass" in url) or ("wialon" in title):
                    return True

            self.log("⛔ Не нашёл вкладку Wialon среди открытых вкладок.")
            return False
        except Exception as e:
            self.log(f"⛔ Ошибка _ensure_on_wialon_tab: {e}")
            return False

    # --- D. Readers:
    def _wait_address_ready(self) -> str | None:
        css = self.selectors["address_selector"]
        end = time.time() + self.ADDRESS_READY_TIMEOUT
        last_text = ""

        while time.time() < end:
            try:
                el = self._safe_find_css(css)
                if not el:
                    time.sleep(0.15)
                    continue
                txt = el.text.strip()
                last_text = txt

                if txt and ("обработка" not in txt.lower()):
                    return txt
            except Exception as e:
                self.log(f"⚠️ Не удалось получить адрес: {self._short_err(e)} -> NavigationBot._wait_address_ready.")
        time.sleep(0.15)
        # если ничего не дождались
        if last_text:
            self.log(f"⚠️ Адрес не готов: '{last_text[:60]}'...")
        return None

    def read_speed_kmh(self) -> int | None:
        css = self.selectors["speed_selector"]
        try:
            el = self._safe_find_css(css)
            if not el:
                return None
            raw = el.text.strip().lower()

            if "км/ч" in raw:
                digits = "".join(filter(str.isdigit, raw))
                return int(digits) if digits else None
            return None
        except Exception as e:
            self.log(f"⚠️ Не удалось получить скорость: {self._short_err(e)}")
            return None

    def _wait_clipboard_coordinates(self, old_value: str = "", timeout: float = None) -> str | None:
        t = timeout or self.CLIPBOARD_TIMEOUT
        end = time.time() + t
        # pattern = re.compile(r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?")

        pattern = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")
        while time.time() < end:
            val = (pyperclip.paste() or "").strip()
            # if val and pattern.search(val):

            if val and val != old_value and pattern.match(val):
                return val
            time.sleep(0.12)
        return None

    def _copy_coordinates(self) -> str | None:
        css_btn = self.selectors["copy_button_selector"]

        old_clip = (pyperclip.paste() or "").strip()
        try:
            pyperclip.copy("")
        except Exception:
            pass

        try:
            btn = self._wait_present_css(css_btn, timeout=8)
            btn.click()
        except Exception as e:
            self.log(f"❌ Не удалось нажать кнопку копирования координат: {self._short_err(e)}")
            return None

        # coord = self._wait_clipboard_coordinates()
        coord = self._wait_clipboard_coordinates(old_value=old_clip)
        if not coord:
            self.log("❌ Координаты не получены из буфера обмена.")
        return coord

    def _read_location_coordinates_speed(self):
        try:
            for i in range(3):
                try:
                    location_text = self._wait_address_ready()
                    coordinates = self._copy_coordinates()
                    speed_kmh = self.read_speed_kmh()

                    if not location_text and not coordinates:
                        return None, None, None

                    return location_text, coordinates, speed_kmh

                except StaleElementReferenceException:
                    self.log(f"🔁 stale при чтении панели, повтор {i + 1}/3")
                    time.sleep(0.2)

        except Exception as e:
            self.log(f"❌ Ошибка чтения гео/коорд/скорости: {self._short_err(e)}")
            return None, None, None

    # ---------- GPS tooltip parsing ----------
    def _extract_fix_line(self, tooltip_text: str) -> str | None:
        if not tooltip_text:
            return None
        lines = [ln.strip() for ln in tooltip_text.splitlines() if ln.strip()]
        if not lines:
            return None

        # приоритет строке "Положение определено ..."
        for ln in lines:
            if "Положение определено" in ln:
                return ln
        # иначе — последняя непустая строка
        return lines[-1]

    def _pasre_age_seconds(self, fix_line: str) -> int | None:
        if not fix_line:
            return None
        pairs = re.findall(r"(\d+)\s*(дн\.?|д\.?|ч\.?|час|часа|часов|мин\.?|м\.?|с\.?)", fix_line.lower())
        if not pairs:
            return None
        total = 0
        for value_str, unit in pairs:
            value = int(value_str)

            if unit.startswith(("с",)):
                total += value
            elif unit.startswith(("м", "мин")):
                total += value * 60
            elif unit.startswith(("ч", "час")):
                total += value * 3600
            elif unit.startswith(("д", "дн")):
                total += value * 86400
        return total

    def _read_gps_fix_age(self, car_id):
        try:
            gps_xpath = self.selectors["gps_sats_xpath"].replace("{car_id}", str(car_id))
            gps_icon = self._wait_visible_xpath(gps_xpath, timeout=10)

            self._hover(gps_icon)
            tooltip_xpath = "//div[@id='tooltip']//div[contains(@class, 'tooltip-gps')]"
            tooltip_el = self._wait_visible_xpath(tooltip_xpath, timeout=10)

            text = (tooltip_el.text or "").strip()
            fix_line = self._extract_fix_line(text)
            age_seconds = self._pasre_age_seconds(fix_line) if fix_line else None

            if fix_line:
                self.log(f"📡 {fix_line}")

            return fix_line, age_seconds

        except Exception as e:
            self.log(f"⚠️ Не удалось получить GPS-tooltip: {self._short_err(e)} -> NavigationBot._read_gps_fix_age")
            return None, None

    def _is_navigation_stale(self, age_second: int | None) -> bool:
        if age_second is None:
            return False
        return age_second >= self.STALE_GPS_SECONDS

    # --- E. Orchestrator
    def get_coordinates_from_wialon(self, car_data: dict) -> dict:
        """ Главный сценарий обработки одной машины"""
        car_number = car_data.get("ТС")
        car_id = car_data.get("id")
        self.log(f"🚗 Обработка ТС {car_number} (ID: {car_id})...")

        # 1) Ввести номер ТС в поиск
        if not self._type_in_search(car_number):
            return car_data

        # 2) Найти элемент машины
        element = self._find_car_element(car_id)
        if not element:
            self.log(f"⚠️ ТС {car_number} не найден.")
            return car_data

        # 3) Проверка ID элемента
        try:
            el_id = element.get_attribute("id") or ""
            if not el_id.endswith(str(car_id)):
                self.log(f"⚠️ ID элемента не совпадает с ожидаемым: {car_id}")
                return car_data
        except StaleElementReferenceException:
            self.log("⚠️ stale при проверке id элемента — пропуск проверки")

        # 4) GPS tooltip age
        gps_text, gps_age = self._read_gps_fix_age(car_id)
        if gps_text:
            car_data["gps_fix_age"] = {"text": gps_text, "age_second": gps_age}

        # 5) Если навигация устарела — выставить маркеры и выйти
        if self._is_navigation_stale(gps_age):
            self.log(f"⛔ Навигация устарела (>{self.STALE_GPS_SECONDS} сек): {gps_text}")
            car_data["гео"] = "нет навигации"
            car_data["коор"] = "!"
            car_data["скорость"] = 0
            car_data["_новые_координаты"] = False
            return car_data

        # 2.1) Найти элемент машины
        element = self._find_car_element(car_id)
        if not element:
            self.log(f"⚠️ ТС {car_number} не найден.")
            return car_data

        # 6) Навести на машину, чтобы обновились панель/адрес
        self._hover(element)

        # 7) Прочитать адрес/координаты/скорость
        geo, coor, speed = self._read_location_coordinates_speed()
        car_data["гео"] = geo
        car_data["коор"] = coor
        car_data["скорость"] = speed

        if coor:
            car_data["_новые_координаты"] = True

        if not coor:
            car_data["_новые_координаты"] = False
            car_data["коор"] = None
        self.log(f"✅ Обработка завершена: {car_number}")
        return car_data

    def process_row(self, car_data: dict, switch_to_wialon: bool = True) -> dict | None:
        try:

            self._ensure_monitoring_open()
            updated = self.get_coordinates_from_wialon(car_data)

            # чистим строку поиска всегда
            self._clear_search()

            if not updated.get("коор"):
                self.log(f"⚠️ Координаты не получены у ТС: {updated.get('ТС')}")
            return updated

        except Exception as e:
            self.log(f"❌ Ошибка в process_row: {self._short_err(e)}")
            return car_data
