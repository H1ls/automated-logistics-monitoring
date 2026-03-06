# Navigation_Bot\bots\wialonReportsBot
import json
import re
import time
from datetime import datetime
from pathlib import Path
from time import sleep

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from LogistX.config.paths import REPORTS_SELECTORS  # путь на wialon_reports_selectors.json


# from Navigation_Bot.core.paths import REPORTS_SELECTORS


class WialonReportsBot:
    REQUIRED_KEYS = [
        "reports_tab_xpath",
        "template_input_xpath",
        "unit_input_xpath",
        "date_from_xpath",
        "date_to_xpath",
        "run_button_xpath",
        "spinner_waiting_css",
        "spinner_loading_css",
        "expand_details_xpath",
        "results_table_css",
        "result_rows_css",
    ]

    DEFAULT_TIMEOUT = 10

    def __init__(self, driver, log_func=print):
        self.driver = driver
        self.log = log_func

        self.sel = self.load_selectors()
        self.validate_selectors()

    # --- A. Init / config
    def load_selectors(self) -> dict:
        try:
            p: Path = REPORTS_SELECTORS
            if not p.exists():
                self.log(f"❌ Нет файла селекторов: {p}")
                return {}
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception as e:
            self.log(f"❌ Ошибка чтения селекторов WialonReports: {e}")
            return {}

    def validate_selectors(self):
        missing = []
        for k in self.REQUIRED_KEYS:
            if k not in self.sel or not self.sel.get(k):
                missing.append(k)
        if missing:
            raise ValueError(f"❌ WialonReportsBot: нет селекторов: {missing}")

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

    def _short_err(self, e: Exception) -> str:
        s = str(e)
        return s[:200] + ("…" if len(s) > 200 else "")

    def _norm(self, s: str) -> str:
        s = (s or "").lower().replace("ё", "е")
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

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

    def _ensure_on_wialon_tab(self):
        try:
            cur = self.driver.current_url or ""
            if "wialon" in cur.lower():
                return
        except Exception:
            pass

        for h in list(self.driver.window_handles):
            try:
                self.driver.switch_to.window(h)
                url = (self.driver.current_url or "").lower()
                if "wialon" in url:
                    return
            except Exception:
                continue

    def open_reports(self):
        """Открыть “Отчёты”"""
        btn = self._wait_clickable_xpath(self.sel["reports_tab_xpath"], timeout=10)
        btn.click()
        # ждём появления фильтра отчёта или хотя бы кнопки "Выполнить"
        self._wait_present_xpath(self.sel["run_button_xpath"], timeout=10)

    def select_template_by_typing(self, name: str):
        """Выбор шаблона (ввод + Enter)"""
        inp = self._wait_present_xpath(self.sel["template_input_xpath"], timeout=10)
        inp.click()
        inp.send_keys(Keys.CONTROL, "a")
        inp.send_keys(name)
        time.sleep(0.25)
        inp.send_keys(Keys.ENTER)

        #  расфокусировка, чтобы список закрылся
        inp.send_keys(Keys.TAB)

        # если всё равно висит -> ESC:
        # inp.send_keys(Keys.ESCAPE)

    @staticmethod
    def _format_license_plate(text: str) -> str:
        # Пример: "Р 211 УР 790" -> "Р211УР790"
        pattern = r'([А-ЯA-Z])\s*(\d{3})\s*([А-ЯA-Z]{2})\s*(\d{2,3})\b'
        m = re.search(pattern, text or "")
        return "".join(m.groups()) if m else (text or "")

    @staticmethod
    def _format_vehicle_line(s: str) -> str:
        """
        'К 774 ТМ 790 SITRAK ZZ4186V391HE' -> 'SITRAK К774ТМ 790'
        """
        PLATE_RE = re.compile(r'^\s*([А-ЯЁ])\s*(\d{3})\s*([А-ЯЁ]{2})\s*(\d{2,3})\b\s*(.+)\s*$', re.IGNORECASE)

        m = PLATE_RE.match(s)
        if not m:
            raise ValueError(f"Не распознал формат строки: {s!r}")

        letter1, digits, letters2, region, tail = m.groups()

        # tail начинается с марки, дальше может быть модель и т.п.
        brand = tail.strip().split()[0].upper()

        plate = f"{letter1.upper()}{digits}{letters2.upper()}"
        return f"{brand} {plate} {region}"

    def select_unit_by_typing(self, unit: str):
        try:  # сначала пробуем как input по xpath
            el = self._wait_present_xpath(self.sel["unit_input_xpath"], timeout=10)
        except Exception:
            el = self._wait_present_xpath(self.sel["unit_input_fallback_xpath"], timeout=10)
        try:  # если это контейнер, найдём input внутри
            inp = el.find_element(By.CSS_SELECTOR, "input")
        except Exception:
            inp = el

        # unit = self._format_license_plate(unit)
        unit = self._format_vehicle_line(unit)
        inp.click()
        inp.send_keys(Keys.CONTROL, "a")
        inp.send_keys(unit)
        sleep(0.5)
        inp.send_keys(Keys.DOWN)
        sleep(0.5)
        inp.send_keys(Keys.ENTER)
        inp.send_keys(Keys.TAB)
        sleep(0.05)

    def set_interval(self, date_from: str, date_to: str):
        data = self._wait_present_xpath(self.sel["date_from_xpath"], timeout=10)
        data_to = self._wait_present_xpath(self.sel["date_to_xpath"], timeout=10)

        data.click()
        data.send_keys(Keys.CONTROL, "a")
        data.send_keys(date_from)
        data.send_keys(Keys.ENTER)
        sleep(0.2)

        data_to.click()
        data_to.send_keys(Keys.CONTROL, "a")
        data_to.send_keys(date_to)
        data_to.send_keys(Keys.ENTER)
        sleep(0.2)

    def run_and_wait(self, timeout=45):
        """Ожидание выполнения (spinner / loading icon)"""
        self._wait_clickable_xpath(self.sel["run_button_xpath"], timeout=10).click()

        try:  # иногда спиннер не успевает появиться — поэтому "presence" в try
            self._wait_present_css(self.sel["spinner_waiting_css"], timeout=3)
        except Exception:
            pass

        self._wait_gone_css(self.sel["spinner_waiting_css"], timeout=timeout)  # ждём исчезновения
        self._wait_present_css(self.sel["results_table_css"], timeout=10)  # и появления таблицы результата

    def expand_all_details(self, max_clicks: int = 25):
        """Развернуть детализацию"""
        for _ in range(max_clicks):
            icons = self.driver.find_elements(By.XPATH, self.sel["expand_details_xpath"])
            icons = [i for i in icons if i.is_displayed()]
            if not icons:
                return
            clicked = False
            for ic in icons[:6]:
                try:
                    ic.click()
                    clicked = True
                    time.sleep(0.12)
                except Exception:
                    pass
            if not clicked:
                return

    def extract_times(self, load_zone: str, unload_zone: str) -> dict:
        """Извлечение времен по геозонам"""
        table = self._wait_present_css(self.sel["results_table_css"], timeout=10)
        rows = table.find_elements(By.CSS_SELECTOR, self.sel["result_rows_css"])

        want_load = self._norm(load_zone)
        want_unload = self._norm(unload_zone)

        res = {"load_in": "", "load_out": "", "unload_in": "", "unload_out": ""}

        dt_re = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\b")

        def to_dt(s: str):
            try:
                return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
            except Exception:
                return None

        load_anchor_dt = None

        for tr in rows:
            tds = tr.find_elements(By.CSS_SELECTOR, self.sel.get("row_cells_css", "td"))
            if len(tds) < 4:
                continue

            texts = [(td.text or "").strip() for td in tds]

            time_idxs = [i for i, tx in enumerate(texts) if dt_re.search(tx)]
            if len(time_idxs) < 2:
                continue

            in_i = time_idxs[0]
            out_i = time_idxs[1]
            gf_i = in_i - 1
            if gf_i < 0:
                continue

            gf = self._norm(texts[gf_i])
            time_in = texts[in_i]
            time_out = texts[out_i]

            # 1) Погрузка: фиксируем якорь
            if want_load and gf == want_load and not res["load_in"]:
                res["load_in"] = time_in
                res["load_out"] = time_out
                load_anchor_dt = to_dt(time_in)

            # 2) Выгрузку начинаем искать ТОЛЬКО после погрузки
            if want_unload and gf == want_unload and not res["unload_in"]:
                if not load_anchor_dt:
                    continue  # ⛔️ рано: выгрузка встретилась до погрузки

                out_dt = to_dt(time_out)
                if out_dt and out_dt < load_anchor_dt:
                    continue  # ⛔️ всё ещё "ранняя" выгрузка (на всякий)

                res["unload_in"] = time_in
                res["unload_out"] = time_out

            if res["load_in"] and res["unload_in"]:
                break

        return res

    def run_geo_report_for_trip(self, unit: str,
                                date_from: str, date_to: str,
                                load_zone: str, unload_zone: str,
                                template: str = "Crossing geozones") -> dict:
        """Главный метод"""

        self._ensure_on_wialon_tab()
        # print("Проверка на открытие браузера self._ensure_on_wialon_tab()")

        self._wait_clickable_xpath(self.sel["reports_tab_xpath"], timeout=10).click()
        # print("Переключение на вкладку отчет self._wait_clickable_xpath()")

        self._wait_present_xpath(self.sel["run_button_xpath"], timeout=10)
        # print("self._wait_present_xpath()")

        self.select_template_by_typing(template)
        # print("Ввод Шаблона self._select_template_by_typing()")
        sleep(2)

        self.select_unit_by_typing(unit)
        # print("Ввод ТС self._select_unit_by_typing()")
        sleep(2)

        self.set_interval(date_from, date_to)
        # print("Ввод даты self._set_interval()")
        sleep(2)

        self.run_and_wait(timeout=75)
        # print("Нажатие на Выполнить self.run_and_wait")
        self.expand_all_details()

        return self.extract_times(load_zone, unload_zone)
