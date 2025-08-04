import time
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import CONFIG_JSON

"""TODO Устранить
        1.
        2.Жёсткие sleep'ы
        3.Зависимость от self.driver
"""


class NavigationBot:
    REQUIRED_KEYS = [
        "search_input_xpath",
        "unit_block_xpath",
        "address_selector",
        "copy_button_selector",
        "speed_selector"
    ]

    def __init__(self, driver, log_func=None):
        self.driver = driver
        self.log = log_func or print
        self.json_manager = JSONManager(CONFIG_JSON)
        self.selectors = self.load_selectors()
        self.validate_selectors()

    def load_selectors(self):
        try:
            selectors = JSONManager.get_selectors("wialon_selectors", CONFIG_JSON)
            # self.log("✅ Селекторы Wialon загружены.")
            # print(CONFIG_JSON)
            return selectors
        except Exception as e:
            self.log(f"❌ Ошибка загрузки селекторов: {e}")
            raise

    def validate_selectors(self):
        for key in self.REQUIRED_KEYS:
            if key not in self.selectors or not self.selectors[key]:
                raise ValueError(f"⛔ Отсутствует селектор '{key}' в конфиге")

    def web_driver_wait(self, xpath, timeout=15):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )

    def clean_car(self):
        try:
            # self.log("🧹 Очистка строки поиска...")
            input_element = self.web_driver_wait(self.selectors["search_input_xpath"])
            input_element.click()
            input_element.send_keys(Keys.CONTROL + "a")
            input_element.send_keys(Keys.BACKSPACE)
            self.driver.execute_script("document.activeElement.blur();")
            # self.log("✅ Строка поиска очищена.")
        except:
            self.log(f"❌ Ошибка в clean_car")

    def find_car_element(self, car_id):
        try:
            xpath = self.selectors["unit_block_xpath"].replace("{car_id}", str(car_id))
            return self.web_driver_wait(xpath)
        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Машина с ID {car_id} не найдена: {msg}")
            return None

    def get_location_and_coordinates(self):
        try:
            # self.log("📍 Получение адреса, координат и скорости...")
            location_text = None
            for _ in range(5):
                try:
                    address_el = self.driver.find_element(By.CSS_SELECTOR, self.selectors["address_selector"])
                    text = address_el.text.strip()
                    if text and "Обработка" not in text:
                        location_text = text
                        break
                except:
                    time.sleep(1)

            if not location_text:
                raise Exception("⏳ Адрес не получен.")

            # self.log("📌 Копируем координаты...")
            self.driver.find_element(By.CSS_SELECTOR, self.selectors["copy_button_selector"]).click()
            time.sleep(0.4)
            coordinates = pyperclip.paste().strip()
            if not coordinates or "," not in coordinates:
                raise Exception(f"❌ Координаты не получены: {coordinates}")

            speed_kmh = None
            try:
                speed_el = self.driver.find_element(By.CSS_SELECTOR, self.selectors["speed_selector"])
                raw_speed = speed_el.text.strip().lower()
                if "км/ч" in raw_speed:
                    speed_kmh = int(''.join(filter(str.isdigit, raw_speed)))
            except Exception as e:
                self.log(f"⚠️ Не удалось получить скорость: {e}")
                speed_kmh = None

            self.log(f"✅ Адрес: {location_text}, Координаты: {coordinates}, Скорость: {speed_kmh} км/ч")
            return location_text, coordinates, speed_kmh

        except Exception as e:
            msg = str(e).splitlines()[0]
            self.log(f"❌ Ошибка получения гео/координат/скорости: {msg}")
            return None, None, None

    def get_coordinates_from_wialon(self, car_data: dict) -> dict:
        car_number = car_data.get("ТС")
        car_id = car_data.get("id")
        self.log(f"🚗 Обработка ТС {car_number} (ID: {car_id})...")

        try:
            search_input = self.web_driver_wait(self.selectors["search_input_xpath"], timeout=20)
            time.sleep(0.5)
            search_input.send_keys(car_number)
        except:
            self.log(f"❌ Не удалось ввести номер ТС:{car_number}:{car_id} ")
            return car_data

        element = self.find_car_element(car_id)
        if not element:
            self.log(f"⚠️ ТС {car_number} не найден.")
            return car_data

        if not element.get_attribute("id").endswith(str(car_id)):
            self.log(f"⚠️ ID элемента не совпадает с ожидаемым: {car_id}")
            return car_data

        ActionChains(self.driver).move_to_element(element).perform()

        location_text, coordinates, speed_kmh = self.get_location_and_coordinates()
        car_data["гео"] = location_text
        car_data["коор"] = coordinates
        car_data["скорость"] = speed_kmh
        if coordinates:
            car_data["_новые_координаты"] = True

        self.log(f"✅ Обработка завершена: {car_number}")
        return car_data

    def process_row(self, car_data: dict, switch_to_wialon: bool = True) -> dict:
        try:
            if switch_to_wialon:
                self.log("🌐 Переключение на вкладку Wialon...")
                self.driver.switch_to.window(self.driver.window_handles[0])

            try:
                self.driver.find_element(By.XPATH, "//*[@id='hb_mi_monitoring']").click()
            except:
                self.log("🔁 Мониторинг уже открыт.")

            updated_car = self.get_coordinates_from_wialon(car_data)
            self.clean_car()

            if not updated_car.get("коор"):
                pass
                # self.log(f"⚠️ Координаты не получены у ТС: {updated_car.get('ТС')}")

            return updated_car

        except Exception as e:
            self.log(f"❌ Ошибка в process_row: {e}")
            return car_data
