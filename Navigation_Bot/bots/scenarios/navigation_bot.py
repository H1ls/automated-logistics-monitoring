# Navigation_Bot\bots\scenarios\navigation_bot.py
import re
import time

import pyperclip
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from Navigation_Bot.core.domain.value_objects.navigation_read_result import NavigationReadResult
from Navigation_Bot.bots.navi_bot_base import NaviBase


class NavigationBot(NaviBase):
    # --- настройки поведения ---

    STALE_GPS_SECONDS = 3600  # 1 час
    ADDRESS_READY_TIMEOUT = 12
    CLIPBOARD_TIMEOUT = 2.5

    SELECTOR_SECTION = "wialon_selectors"
    DEFAULT_GEO_ZONE_SELECTOR = ".geo_jYI9"

    REQUIRED_KEYS = ("search_input_xpath",
                     "unit_block_xpath",
                     "address_selector",
                     "copy_button_selector",
                     "speed_selector",
                     "gps_sats_xpath",
                     "monitoring",)

    def __init__(self, driver, log_func=None):
        super().__init__(driver, log_func)

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
            self.log(f"❌ Ошибка очистки поля ввода ТС,  _clear_search")

    def _type_in_search(self, text: str) -> bool:
        try:
            search_input = self._focus_search_input()
            search_input.click()
            self._clear_search()  # Удалить перед вводом
            search_input.send_keys(text)
            # el = self.selectors["move_to_element"]
            # ActionChains(self.driver).move_to_element(el).perform()
            self.driver.execute_script("document.activeElement.blur();")
            return True
        except Exception as e:
            self.log(
                f"❌ Не удалось ввести текст в поиск '{text}':  -> NavigationBot._type_in_search")
            # self.log({self._short_err(e)})
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
            self.log(f"❌ Машина с ID {car_id} не найдена: -> NavigationBot._find_car_element")
            # self.log({self._short_err(e)} )
            return None

    def _ensure_monitoring_open(self) -> None:
        try:
            btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@id='hb_mi_monitoring']")))
            btn.click()
            self.log("📡 Открыт 'Мониторинг'.")
        except Exception:
            pass

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
                self.log(f"⚠️ Не удалось получить адрес: -> NavigationBot._wait_address_ready.")
                self.log(f"{self._short_err(e)}.")
        time.sleep(0.15)
        # если ничего не дождались
        if last_text:
            self.log(f"⚠️ Адрес не готов: '{last_text[:60]}'...")
        return None

    def _read_geo_zona(self) -> str | None:
        """Геозона Wialon (класс geo_jYI9 на панели объекта)."""
        css = self.selectors.get("geo_zone_selector") or self.DEFAULT_GEO_ZONE_SELECTOR
        try:
            el = self._safe_find_css(css)
            if not el:
                return None
            text = (el.text or "").strip()
            return text or None
        except Exception:
            self.log("⚠️ Не удалось прочитать geo_zona")
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
            self.log(f"⚠️ Не удалось получить скорость: ")
            # self.log(f"{self._short_err(e)}")
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
            self.log(f"❌ Не удалось нажать кнопку копирования координат: ")
            # self.log(f" {self._short_err(e)}")
            return None

        coord = self._wait_clipboard_coordinates(old_value=old_clip)
        if not coord:
            self.log("❌ Координаты не получены из буфера обмена.")
        return coord

    def _read_location_coordinates_speed(
            self,
    ) -> tuple[str | None, str | None, int | None, str | None]:
        """Адрес, координаты, скорость и геозона с панели объекта."""
        try:
            for i in range(3):
                try:
                    location_text = self._wait_address_ready()
                    coordinates = self._copy_coordinates()
                    speed_kmh = self.read_speed_kmh()
                    geo_zona = self._read_geo_zona()

                    if not location_text and not coordinates:
                        return None, None, None, geo_zona

                    return location_text, coordinates, speed_kmh, geo_zona

                except StaleElementReferenceException:
                    self.log(f"🔁 stale при чтении панели, повтор {i + 1}/3")
                    time.sleep(0.2)

            return None, None, None, None

        except Exception:
            self.log("❌ Ошибка чтения гео/коорд/скорости/geo_zona")
            return None, None, None, None

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

    def _parse_age_seconds(self, fix_line: str) -> int | None:
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
            age_seconds = self._parse_age_seconds(fix_line) if fix_line else None

            if fix_line:
                self.log(f"📡 {fix_line}")

            return fix_line, age_seconds

        except Exception as e:
            self.log(f"⚠️ Не удалось получить GPS-tooltip: -> NavigationBot._read_gps_fix_age")
            # self.log(f"⚠️ Не удалось получить GPS-tooltip: {self._short_err(e)} -> NavigationBot._read_gps_fix_age")
            return None, None

    def _is_navigation_stale(self, age_second: int | None) -> bool:
        if age_second is None:
            return False
        return age_second >= self.STALE_GPS_SECONDS

    # --- E. Orchestrator
    # TODO: исправить 5 пункт с получением Координаты,
    #       сейчас ошибка при последовательном повторном вызове одной и той же ТС
    def read_navigation_state(self, car_data: dict) -> NavigationReadResult | None:
        car_number = car_data.get("ТС")
        car_id = car_data.get("id")

        self.log(f"🚗 Обработка ТС {car_number} (ID: {car_id})...")

        # 1) Ввести номер ТС в поиск
        if not self._type_in_search(car_number):
            return None

        # 2) Найти элемент машины
        element = self._find_car_element(car_id)
        if not element:
            self.log(f"⚠️ ТС {car_number} не найден.")
            return None

        # 3) Проверка ID элемента
        try:
            el_id = element.get_attribute("id") or ""
            if not el_id.endswith(str(car_id)):
                self.log(f"⚠️ ID элемента не совпадает с ожидаемым: {car_id}")
                return None
        except StaleElementReferenceException:
            self.log("⚠️ stale при проверке id элемента — пропуск проверки")

        # 4) GPS tooltip age

        gps_text, gps_age = self._read_gps_fix_age(car_id)
        is_stale = self._is_navigation_stale(gps_age)

        if is_stale:
            self.log(f"⛔ Навигация устарела (>{self.STALE_GPS_SECONDS} сек): {gps_text}")
            return NavigationReadResult(gps_fix_text=gps_text or "",
                                        gps_fix_age_seconds=gps_age,
                                        geo_text="нет навигации",
                                        geo_zona="",
                                        coordinates="!",
                                        speed_kmh=0,
                                        has_fresh_coordinates=False,
                                        is_navigation_stale=True,
                                        )

        # 5) Повторно берём элемент и читаем панель
        element = self._find_car_element(car_id)
        if not element:
            self.log(f"⚠️ ТС {car_number} не найден.")
            return None

        self._hover(element)

        geo, coor, speed, geo_zona = self._read_location_coordinates_speed()

        return NavigationReadResult(gps_fix_text=gps_text or "",
                                    gps_fix_age_seconds=gps_age,
                                    geo_text=geo or "",
                                    geo_zona=geo_zona or "",
                                    coordinates=coor if coor else None,
                                    speed_kmh=speed,
                                    has_fresh_coordinates=bool(coor),
                                    is_navigation_stale=False,
                                    )

    def process_vehicle_row(self, car_data: dict) -> NavigationReadResult | None:
        try:
            self._ensure_monitoring_open()
            result = self.read_navigation_state(car_data)
            self._clear_search()

            if result and not result.coordinates:
                self.log(f"⚠️ Координаты не получены у ТС: {car_data.get('ТС')}")
            return result

        except Exception as e:
            self.log(f"❌ Ошибка в process_vehicle_row: {self._short_err(e)}")
        return None
