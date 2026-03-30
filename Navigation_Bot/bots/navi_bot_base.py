import json
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import CONFIG_JSON
from pathlib import Path


class NaviBase:
    """Общая база для ботов Wialon: драйвер, лог, ожидания элементов, вкладка Wialon."""
    DEFAULT_TIMEOUT = 10
    SELECTOR_SECTION = None
    SELECTOR_PATH = None
    REQUIRED_KEYS = ()

    def __init__(self, driver, log_func=None):

        self.driver = driver
        self.log = log_func or print
        self.selectors = self.load_selectors()
        self.validate_selectors()

    # --- A. Init / config
    def load_selectors(self) -> dict:
        try:
            if self.SELECTOR_SECTION:
                data = JSONManager.get_selectors(self.SELECTOR_SECTION, CONFIG_JSON)
                return data if isinstance(data, dict) else {}

            if self.SELECTOR_PATH:
                p = Path(self.SELECTOR_PATH)
                if not p.exists():
                    self.log(f"❌ Нет файла селекторов: {p}")
                    return {}
                data = json.loads(p.read_text(encoding="utf-8") or "{}")
                return data if isinstance(data, dict) else {}

            raise ValueError(f"{self.__class__.__name__}: не задан источник селекторов")

        except Exception as e:
            self.log(f"❌ Ошибка загрузки селекторов {self.__class__.__name__}: {self._short_err(e)}")
            return {}

    def validate_selectors(self) -> None:
        missing = [key for key in self.REQUIRED_KEYS if not self.selectors.get(key)]
        if missing:
            raise ValueError(f"⛔ {self.__class__.__name__}: отсутствуют селекторы: {missing}")

    # --- B. Selenium helpers
    def _wait_visible_xpath(self, xpath: str, timeout: int = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(
            EC.visibility_of_element_located((By.XPATH, xpath)))

    def _wait_present_css(self, css: str, timeout: int = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css)))

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

    # --WialonReportsBot
    def _wait_present_xpath(self, xpath: str, timeout: int | None = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(
            EC.presence_of_element_located((By.XPATH, xpath)))

    def _wait_clickable_xpath(self, xpath: str, timeout: int | None = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(
            EC.element_to_be_clickable((By.XPATH, xpath)))

    def _wait_gone_css(self, css: str, timeout: int | None = None):
        t = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, t).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, css)))

    def _ensure_on_wialon_tab(self) -> bool:
        try:
            url = (self.driver.current_url or "").lower()
            title = (self.driver.title or "").lower()
            # if ("wialon" in url) or ("rtmglonass" in url) or ("wialon" in title):
            if ("gps.skyglonass" in url) or ("rtmglonass" in url) or ("wialon" in title):
                return True

            # если сейчас не Wialon — попробуем найти вкладку среди всех
            for h in self.driver.window_handles:
                self.driver.switch_to.window(h)
                url = (self.driver.current_url or "").lower()
                title = (self.driver.title or "").lower()
                # if ("wialon" in url) or ("rtmglonass" in url) or ("wialon" in title):
                if ("gps.skyglonass" in url) or ("rtmglonass" in url) or ("wialon" in title):
                    return True

            self.log("⛔ Не нашёл вкладку Wialon среди открытых вкладок.")
            return False
        except Exception as e:
            self.log(f"⛔ Ошибка _ensure_on_wialon_tab: {e}")
            return False
