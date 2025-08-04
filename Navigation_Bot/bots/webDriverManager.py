import time
import json
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

"""6. Настройка WebDriver"""
"""TO DO 1. чтение json -> JSONManager
        2. Проверка авторизация - True/Fasle
        3. Сначала куки потом авторизация self.driver.get(...)self.load_cookies()self.driver.refresh()
        

"""


class WebDriverManager:
    def __init__(self, log_func=None):
        self.log = log_func or print
        self.config_path = "../config/Credentials_wialon.json"
        self.cookies_path = "../config/cookies.pkl"
        self.driver = None

    def web_driver_wait(self, xpath, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )

    def start_browser(self):
        self.driver = webdriver.Chrome()
        self.driver.maximize_window()
        self.log("✅ Браузер запущен.")

    def save_cookies(self):
        with open(self.cookies_path, "wb") as file:
            pickle.dump(self.driver.get_cookies(), file)

    def load_cookies(self):
        try:
            with open(self.cookies_path, "rb") as file:
                cookies = pickle.load(file)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            self.log("Куки загружены.")
        except FileNotFoundError:
            self.log("Файл cookies.pkl не найден, требуется авторизация.")

    def open_wialon(self):
        self.driver.get("https://wialon.rtmglonass.ru/?lang=ru")
        self.load_cookies()
        self.driver.refresh()
        self.log("Виалон открывается")
        time.sleep(5)

    def setup_wialon(self):
        try:
            self.web_driver_wait("//*[@id='hb_mi_monitoring']").click()
        except:
            self.log(f'в "class WebDriverManager -> setup_wialon"\n Не смог найти class=hb_item_text')

    def login_wialon(self):
        """Авторизуется в Wialon, если нет сохранённых cookies"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        username = data["login"]["username"]
        password = data["login"]["password"]

        self.driver.get("https://wialon.rtmglonass.ru/?lang=ru")

        self.web_driver_wait("//*[@data-testid='LoginMainEmailInput']").send_keys(username)
        self.web_driver_wait("//*[@data-testid='LoginMainPassInput']").send_keys(password)

        login_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@data-testid='LoginMainSubmitButton']"))
        )
        login_button.click()

        # self.log("Авторизация в Wialon")
        self.save_cookies()
        # self.log("🔐 Авторизация в Wialon...")
        try:
            self.web_driver_wait("//*[@id='hb_mi_monitoring']").click()
        except:
            self.log(f'в "class WebDriverManager -> login_wialon"\n Не смог найти class=hb_item_text')

    def open_yandex_maps(self):
        # self.log("🗺️ Проверка вкладок с Яндекс.Картами...")

        try:
            for handle in self.driver.window_handles:
                self.driver.switch_to.window(handle)
                current_url = self.driver.current_url.lower()
                title = self.driver.title.lower()

                if ("yandex" in current_url and "maps" in current_url) or \
                        ("yandex" in title or "яндекс" in title):
                    self.log("🔁 Найдена вкладка Яндекс.Карт — переключаемся.")
                    return  # уже открыта и активирована

            # Не нашли — открываем новую
            # self.log("➕ Открытие новой вкладки с Я.Картами...")
            self.driver.execute_script("window.open('https://yandex.ru/maps', '_blank');")
            time.sleep(1)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
            # self.log("🗺️ Новая вкладка Я.Карт открыта.")

        except Exception as e:
            self.log(f"❌ Ошибка при открытии Я.Карт: {e}")
