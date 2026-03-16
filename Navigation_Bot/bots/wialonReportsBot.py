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
    REQUIRED_KEYS = ["reports_tab_xpath",
                     "template_input_xpath",
                     "unit_input_xpath",
                     "date_from_xpath",
                     "date_to_xpath",
                     "run_button_xpath",
                     "spinner_waiting_css",
                     "spinner_loading_css",
                     "expand_details_xpath",
                     "results_table_css",
                     "result_rows_css", ]
    MIN_STAY_SECONDS = 120  # всё что меньше 2 минут — шум
    MERGE_GAP_SECONDS = 900  # разрыв до 15 минут — считаем одним пребыванием
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
        sleep(0.5)
        # если всё равно висит -> ESC:
        # inp.send_keys(Keys.ESCAPE)

    @staticmethod
    def _format_vehicle_line(s: str) -> str:
        """
        'К 774 ТМ 790 SITRAK ZZ4186V391HE' -> 'SITRAK К774ТМ 790'
        'Е 193 УА 790 Mercedes-Benz Actros 1848' -> 'MERCEDES Е193УА 790'
        """
        PLATE_RE = re.compile(
            r'^\s*([А-ЯЁ])\s*(\d{3})\s*([А-ЯЁ]{2})\s*(\d{2,3})\b\s*(.+)\s*$', re.IGNORECASE)
        m = PLATE_RE.match(s)
        if not m:
            raise ValueError(f"Не распознал формат строки: {s!r}")
        letter1, digits, letters2, region, tail = m.groups()
        brand_raw = tail.strip().split()[0]
        # убираем всё после дефиса (Mercedes-Benz -> Mercedes)
        brand = brand_raw.split("-")[0].upper()
        plate = f"{letter1.upper()}{digits}{letters2.upper()}"
        return f"{brand} {plate} {region}"

    def select_unit_by_typing(self, unit: str):
        """Ввод (марки и номера) машины"""
        try:  # сначала пробуем как input по xpath
            el = self._wait_present_xpath(self.sel["unit_input_xpath"], timeout=10)
        except Exception:
            el = self._wait_present_xpath(self.sel["unit_input_fallback_xpath"], timeout=10)
        try:  # если это контейнер, найдём input внутри
            inp = el.find_element(By.CSS_SELECTOR, "input")
        except Exception:
            inp = el

        unit = self._format_vehicle_line(unit)
        inp.click()
        inp.send_keys(Keys.CONTROL, "a")
        inp.send_keys(unit)
        sleep(0.5)
        inp.send_keys(Keys.DOWN)
        sleep(0.5)
        inp.send_keys(Keys.ENTER)
        inp.send_keys(Keys.TAB)
        sleep(0.5)

    def set_interval(self, date_from: str, date_to: str):
        """Ввод даты начала рейса, и конца текущего дня"""
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
        sleep(0.7)

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
        """Извлечение времен по геозонам с защитой от дребезга навигации."""
        table = self._wait_present_css(self.sel["results_table_css"], timeout=10)
        rows = table.find_elements(By.CSS_SELECTOR, self.sel["result_rows_css"])

        want_load = self._norm(load_zone)
        want_unload = self._norm(unload_zone)

        res = {"load_in": "", "load_out": "", "unload_in": "", "unload_out": ""}

        dt_re = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\b")

        MIN_STAY_SECONDS = 120  # менее 2 минут считаем шумом
        MERGE_GAP_SECONDS = 900  # разрыв до 15 минут склеиваем

        def to_dt(s: str):
            try:
                return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
            except Exception:
                return None

        visits = []

        # 1. Собираем все посещения
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

            in_dt = to_dt(time_in)
            out_dt = to_dt(time_out)
            if not in_dt or not out_dt:
                continue

            stay_sec = int((out_dt - in_dt).total_seconds())
            if stay_sec < 0:
                continue

            visits.append({"gf": gf,
                           "in": time_in,
                           "out": time_out,
                           "in_dt": in_dt,
                           "out_dt": out_dt,
                           "stay_sec": stay_sec, })

        if not visits:
            return res

        # 2. Фильтруем короткий шум
        filtered = []
        for v in visits:
            if v["stay_sec"] < MIN_STAY_SECONDS:
                self.log(f"⚠️ Игнорирую короткое посещение как шум: {v['gf']} {v['in']} -> {v['out']}")
                continue
            filtered.append(v)

        if not filtered:
            return res

        # 3. Склеиваем соседние посещения одной геозоны, если разрыв маленький
        merged = []
        for v in filtered:
            if not merged:
                merged.append(v.copy())
                continue

            prev = merged[-1]

            same_zone = prev["gf"] == v["gf"]
            gap_sec = int((v["in_dt"] - prev["out_dt"]).total_seconds())

            if same_zone and 0 <= gap_sec <= MERGE_GAP_SECONDS:
                prev["out"] = v["out"]
                prev["out_dt"] = v["out_dt"]
                prev["stay_sec"] = int((prev["out_dt"] - prev["in_dt"]).total_seconds())
                self.log(f"🔗 Склеил дребезг геозоны: {prev['gf']} до {prev['out']}")
            else:
                merged.append(v.copy())

        # 4. Особый случай: погрузка и выгрузка в одной геозоне
        if want_load and want_unload and want_load == want_unload:
            same_zone_visits = [v for v in merged if v["gf"] == want_load]
            if same_zone_visits:
                first_visit = same_zone_visits[0]
                res["load_in"] = first_visit["in"]
                res["load_out"] = first_visit["out"]

                if len(same_zone_visits) >= 2:
                    last_visit = same_zone_visits[-1]
                    res["unload_in"] = last_visit["in"]
                    res["unload_out"] = last_visit["out"]

            return res

        # 5. Обычный случай: разные геозоны
        load_visit = None

        for v in merged:
            if not load_visit and want_load and v["gf"] == want_load:
                load_visit = v
                res["load_in"] = v["in"]
                res["load_out"] = v["out"]
                continue

            if load_visit and want_unload and v["gf"] == want_unload:
                if v["out_dt"] >= load_visit["in_dt"]:
                    res["unload_in"] = v["in"]
                    res["unload_out"] = v["out"]
                    break

        return res

    def run_geo_report_for_trip(self, unit: str,
                                date_from: str, date_to: str,
                                load_zone: str, unload_zone: str,
                                template: str = "Crossing geozones") -> dict:
        """Главный метод"""
        self._ensure_on_wialon_tab()

        self._wait_clickable_xpath(self.sel["reports_tab_xpath"], timeout=10).click()

        self._wait_present_xpath(self.sel["run_button_xpath"], timeout=10)

        self.select_template_by_typing(template)

        self.select_unit_by_typing(unit)

        self.set_interval(date_from, date_to)

        self.run_and_wait(timeout=75)
        self.expand_all_details()

        return self.extract_times(load_zone, unload_zone)
