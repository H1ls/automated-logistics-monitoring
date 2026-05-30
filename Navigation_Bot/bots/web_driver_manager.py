import json
import pickle
import time

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, InvalidSessionIdException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from contextlib import contextmanager
from selenium.webdriver.chrome.options import Options as ChromeOptions

from Navigation_Bot.core.secrets_manager import SecretsManager
from Navigation_Bot.core.paths import CREDENTIALS_WIALON, COOKIES_FILE

"""6. Настройка WebDriver"""

# TODO: 1. чтение json -> JSONManager

WIALON_URL = "https://gps.skyglonass.ru/"
YANDEX_MAPS_URL = "https://yandex.ru/maps"


class WebDriverManager:
    def __init__(self, log_func=None):
        self.log = log_func or print
        self.config_path = str(CREDENTIALS_WIALON)
        self.cookies_path = str(COOKIES_FILE)
        self.driver = None
        self.secrets = SecretsManager()

    def _login_wialon(self):
        """Авторизуется в Wialon, используя env переменные"""
        try:
            username, password = self.secrets.get_wialon_credentials()

            # Остальной код без изменений
            self.web_driver_wait("//*[@data-testid='LoginMainEmailInput']").send_keys(username)
            self.web_driver_wait("//*[@data-testid='LoginMainPassInput']").send_keys(password)
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@data-testid='LoginMainSubmitButton']")))
            login_button.click()
            # self.save_cookies()

            clicked = False
            for attempt in range(10):
                try:
                    btn = self.web_driver_wait("//*[@id='hb_mi_monitoring']", timeout=3)
                    btn.click()
                    self.log("📡 Открыт 'Мониторинг'.")
                    clicked = True
                    break
                except TimeoutException:
                    self.log(f"⌛ Ожидаем появление 'Мониторинг'... (попытка {attempt + 1})")
                    time.sleep(1)

            if not clicked:
                self.log("⚠️ Не удалось кликнуть 'Мониторинг' после логина.")
        except ValueError as e:
            self.log(f"❌ Ошибка credentials: {e}")
            raise
        except Exception as e:
            self.log(f"❌ Ошибка при логине в Wialon ")
            # self.log(f"❌ Ошибка при логине в Wialon:\n {e}")

    def stop_browser(self):
        """Остановка браузера"""
        try:
            if self.driver:
                self.driver.quit()
                self.log("✅ WebDriver закрыт")
        except Exception as e:
            self.log(f"⚠️ Ошибка при закрытии WebDriver: {e}")
        finally:
            self.driver = None

    @contextmanager
    def get_driver_context(self, rect=None):
        """Context manager для гарантированной очистки WebDriver"""
        try:
            # Стартуем браузер
            self.start_browser(rect=rect)
            yield self.driver
        except Exception as e:
            self.log(f"❌ Ошибка в браузере: {e}")
            # даже если ошибка, finally выполнится
            raise
        finally:
            # Выполнится всегда, даже при исключении
            self.stop_browser()

    def web_driver_wait(self, xpath, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath)))

    @staticmethod
    def _is_wialon_tab(url: str, title: str) -> bool:
        url = (url or "").lower()
        title = (title or "").lower()
        return ("gps.skyglonass" in url
                or "rtmglonass" in url
                or "wialon" in title
                or "skytelecom" in title
                )

    @staticmethod
    def _is_yandex_maps_tab(url: str, title: str) -> bool:
        url = (url or "").lower()
        title = (title or "").lower()
        return ("yandex" in url and "maps" in url) or ("yandex" in title or "яндекс" in title)

    def _switch_to_first_alive_window(self) -> bool:
        """Переключается на первую доступную вкладку (если текущая была закрыта)."""
        d = self.driver
        if not d:
            return False
        try:
            handles = d.window_handles
        except (InvalidSessionIdException, WebDriverException):
            return False
        for handle in handles:
            try:
                d.switch_to.window(handle)
                _ = d.current_url
                return True
            except (InvalidSessionIdException, WebDriverException):
                continue
        return False

    def is_alive(self) -> bool:
        """Проверка живой ли WebDriver (закрытие одной вкладки не считается смертью сессии)."""
        d = getattr(self, "driver", None)
        if not d:
            return False
        try:
            if not d.window_handles:
                return False
            return self._switch_to_first_alive_window()
        except (InvalidSessionIdException, WebDriverException):
            return False

    def start_browser(self, rect=None):
        """Стартуем Chrome, гарантируя что старый браузер закрыт"""
        # Закрываем старый браузер ДО запуска нового, (даже если is_alive() вернул False, процесс может зомби-статусе)
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

        # гарантированно запускаем новый браузер
        try:
            options = ChromeOptions()
            # Опционально для headless: options.add_argument('--headless')
            self.driver = webdriver.Chrome(options=options)

            if rect:
                try:
                    self.driver.set_window_rect(rect.get("x", 0),
                                                rect.get("y", 0),
                                                rect.get("width", 1024),
                                                rect.get("height", 768))
                except Exception as e:
                    self.log(f"⚠️ Не удалось установить позицию окна: {e}")
                    self.driver.maximize_window()

            # self.log("✅ Новый браузер запущен")
        except Exception as e:
            self.driver = None
            self.log(f"❌ Не удалось запустить браузер: {e}")
            raise

    def save_cookies(self):
        try:
            with open(self.cookies_path, "wb") as file:
                pickle.dump(self.driver.get_cookies(), file)
            self.log("💾 Куки сохранены")
        except Exception as e:
            self.log(f"❌ Ошибка при сохранении cookies: {e}")

    def load_cookies(self):
        try:
            with open(self.cookies_path, "rb") as file:
                cookies = pickle.load(file)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            # self.log("🍪 Куки загружены.")
            return True
        except FileNotFoundError:
            self.log("⚠️ Файл cookies.pkl не найден, потребуется авторизация")
            return False
        except Exception as e:
            self.log(f"❌ Ошибка загрузки cookies ")
            # self.log(f"❌ Ошибка загрузки cookies:\n {e}")
            return False

    def _find_tab(self, *, wialon: bool = False, yandex: bool = False) -> bool:
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            url = self.driver.current_url or ""
            title = self.driver.title or ""
            if wialon and self._is_wialon_tab(url, title):
                return True
            if yandex and self._is_yandex_maps_tab(url, title):
                return True
        return False

    def login_wialon(self, *, new_tab: bool = False):
        """Открывает/логинит Wialon и переключает на мониторинг."""
        if new_tab:
            self.driver.execute_script(f"window.open('{WIALON_URL}', '_blank');")
            time.sleep(0.5)
            self.driver.switch_to.window(self.driver.window_handles[-1])
        else:
            self.driver.get(WIALON_URL)

        if self.load_cookies():
            self.driver.refresh()

        try:
            self.web_driver_wait("//*[@id='hb_mi_monitoring']", timeout=1)
            self.log("🔑 Авторизация уже выполнена (по cookies).")
        except TimeoutException:
            self._login_wialon()

    def open_yandex_maps(self):
        try:
            if self._find_tab(yandex=True):
                self.log("🔁 Найдена вкладка Яндекс.Карт — переключаемся")
                return

            self.log("➕ Открываю новую вкладку с Я.Картами...")
            self.driver.execute_script(f"window.open('{YANDEX_MAPS_URL}', '_blank');")
            time.sleep(2)
            self.driver.switch_to.window(self.driver.window_handles[-1])

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body")))
            self.log("🗺️ Новая вкладка Я.Карт открыта")

        except Exception:
            self.log("❌ Ошибка при открытии Я.Карт")

    def ensure_wialon_tab(self) -> None:
        """Восстанавливает вкладку Wialon в уже открытом Chrome (без перезапуска браузера)."""
        if self._find_tab(wialon=True):
            return
        # Если Я.Карты (или другие вкладки) уже открыты — не трогаем их, открываем Wialon отдельно.
        use_new_tab = self._find_tab(yandex=True) or len(self.driver.window_handles) > 1
        self.log("➕ Вкладка Wialon не найдена — открываю "
                 + ("в новой вкладке..." if use_new_tab else "в текущей вкладке...")
                 )
        self.login_wialon(new_tab=use_new_tab)

    def ensure_yandex_tab(self) -> None:
        """Восстанавливает вкладку Я.Карт в уже открытом Chrome."""
        self.open_yandex_maps()

    def ensure_required_tabs(self) -> None:
        """Гарантирует наличие вкладок Wialon и Я.Карт."""
        if not self.driver or not self.is_alive():
            return
        self._switch_to_first_alive_window()
        self.ensure_wialon_tab()
        self.ensure_yandex_tab()

    def switch_to_tab(self, name: str) -> bool:
        try:
            if not self.driver:
                return False
            self._switch_to_first_alive_window()

            wanted = (name or "").lower().strip()
            is_wialon = wanted in {"wialon", "gps.skyglonass", "skyglonass", "rtmglonass"}
            is_yandex = wanted == "yandex"

            if is_wialon and self._find_tab(wialon=True):
                return True
            if is_yandex and self._find_tab(yandex=True):
                return True

            if is_wialon:
                self.log("ℹ️ Вкладка Wialon не найдена — восстанавливаю...")
                self.ensure_wialon_tab()
                return self._find_tab(wialon=True)

            if is_yandex:
                self.log("ℹ️ Вкладка 'yandex' не найдена — восстанавливаю...")
                self.ensure_yandex_tab()
                return self._find_tab(yandex=True)

            self.log(f"❌ Вкладка '{name}' не найдена.")
            return False

        except Exception:
            self.log(f"❌ Ошибка переключения на вкладку {name}")
            return False

    def find(self, locator, timeout=10, condition="presence"):
        conditions = {"presence": EC.presence_of_element_located,
                      "visible": EC.visibility_of_element_located,
                      "clickable": EC.element_to_be_clickable}

        cond = conditions.get(condition, EC.presence_of_element_located)
        return WebDriverWait(self.driver, timeout).until(cond(locator))

    def find_all(self, locator, timeout=10):
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_all_elements_located(locator))

        return self.driver.find_elements(*locator)

    def click(self, locator, timeout=10):
        el = self.find(locator, timeout, condition="clickable")
        el.click()
        return el

    def execute_js(self, script, element=None):
        return self.driver.execute_script(script, element)
