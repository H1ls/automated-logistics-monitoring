from config.requirements import *

"""6. Настройка WebDriver"""


class WebDriverManager:
    def __init__(self):
        self.config_path = "config/config.json"
        self.cookies_path = "config/cookies.pkl"
        self.driver = None

    def start_browser(self):
        self.driver = webdriver.Chrome()
        self.driver.maximize_window()

    def save_cookies(self):
        with open(self.cookies_path, "wb") as file:
            pickle.dump(self.driver.get_cookies(), file)

    def load_cookies(self):
        try:
            with open(self.cookies_path, "rb") as file:
                cookies = pickle.load(file)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            print("Куки загружены.")
        except FileNotFoundError:
            print("Файл cookies.pkl не найден, требуется авторизация.")

    def web_driver_wait(self, xpath, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )

    def open_wialon(self):
        self.driver.get("https://wialon.rtmglonass.ru/?lang=ru")
        self.load_cookies()
        self.driver.refresh()
        time.sleep(5)

    def login_wialon(self):
        """Авторизуется в Wialon, если нет сохранённых cookies"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        username = data["username"]
        password = data["password"]

        self.driver.get("https://wialon.rtmglonass.ru/?lang=ru")

        self.web_driver_wait("//*[@data-testid='LoginMainEmailInput']").send_keys(username)
        self.web_driver_wait("//*[@data-testid='LoginMainPassInput']").send_keys(password)

        login_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@data-testid='LoginMainSubmitButton']"))
        )
        login_button.click()

        print("Авторизация в Wialon")
        self.save_cookies()

    def open_yandex_maps(self):
        self.driver.get("https://yandex.ru/maps")  # Открываем карты в текущей вкладке

        try:
            # Ожидание полной загрузки страницы
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Проверяем, есть ли кнопка "Построить маршрут"
            route_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@class, 'button _view_search _size_medium _link')]"))
            )
            route_button.click()
        except TimeoutException:
            print("Кнопка маршрута не найдена")

    def setup_wialon(self):
        try:
            self.web_driver_wait("//*[@id='hb_mi_monitoring']").click()
        except:
            print(f'в "class WebDriverManager -> setup_wialon"\n Не смог найти class=hb_item_text')