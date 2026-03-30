# Navigation_Bot\bots\scenarios\ReportsBot.py

import re
import time
from datetime import datetime
from time import sleep

from selenium.common.exceptions import (ElementClickInterceptedException, StaleElementReferenceException,
                                        TimeoutException, )
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from Navigation_Bot.bots.navi_bot_base import NaviBase
from LogistX.config.paths import REPORTS_SELECTORS


class WialonReportsBot(NaviBase):
    SELECTOR_PATH = REPORTS_SELECTORS
    MIN_STAY_SECONDS = 120  # всё что меньше 2 минут — шум
    MERGE_GAP_SECONDS = 900  # разрыв до 15 минут — считаем одним пребыванием
    REQUIRED_KEYS = ("reports_tab_xpath",
                     "template_input_xpath",
                     "unit_input_xpath",
                     "date_from_xpath",
                     "date_to_xpath",
                     "run_button_xpath",
                     "spinner_waiting_css",
                     "spinner_loading_css",
                     "expand_details_xpath",
                     "results_table_css",
                     "result_rows_css",)


    def __init__(self, driver, log_func=print):
        super().__init__(driver, log_func)

    def _norm(self, s: str) -> str:
        s = (s or "").lower().replace("ё", "е")
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _zone_match(self, got: str, want: str) -> bool:
        got_n = self._norm(got)
        want_n = self._norm(want)

        if not got_n or not want_n:
            return False

        return (got_n == want_n
                or got_n in want_n
                or want_n in got_n)

    def _wait_page_settled(self, timeout: int | None = None):
        t = timeout or self.DEFAULT_TIMEOUT
        try:
            WebDriverWait(self.driver, t).until(lambda d: d.execute_script("return document.readyState") == "complete")
        except Exception:
            pass

        # если есть спиннеры — ждём их исчезновения
        for css_key in ("spinner_waiting_css", "spinner_loading_css"):
            css = self.selectors.get(css_key)
            if not css:
                continue
            try:
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, css)))
            except Exception:
                pass

    def _safe_click_xpath(self, xpath: str, timeout: int | None = None, name: str = ""):
        t = timeout or self.DEFAULT_TIMEOUT
        last_err = None

        for attempt in range(1, 4):
            try:
                self._wait_page_settled(timeout=5)
                el = WebDriverWait(self.driver, t).until(EC.presence_of_element_located((By.XPATH, xpath)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
                time.sleep(0.15)
                WebDriverWait(self.driver, t).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                try:
                    el.click()
                    return el
                except ElementClickInterceptedException as e:
                    last_err = e
                try:
                    ActionChains(self.driver).move_to_element(el).pause(0.1).click(el).perform()
                    return el
                except Exception as e:
                    last_err = e
                try:
                    self.driver.execute_script("arguments[0].click();", el)
                    return el
                except Exception as e:
                    last_err = e

            except (ElementClickInterceptedException, StaleElementReferenceException, TimeoutException) as e:
                last_err = e
                self.log(f"⚠️ safe click retry {attempt}/3 [{name or xpath}]: {self._short_err(e)}")
                time.sleep(0.4)
        if last_err:
            raise last_err
        raise RuntimeError(f"safe click failed: {name or xpath}")

    def open_reports(self):
        """Открыть “Отчёты”"""
        self._safe_click_xpath(self.selectors["reports_tab_xpath"], timeout=10, name="reports_tab")
        # ждём появления фильтра отчёта или хотя бы кнопки "Выполнить"
        self._wait_present_xpath(self.selectors["run_button_xpath"], timeout=10)

    def select_template_by_typing(self, name: str):
        inp = self._wait_present_xpath(self.selectors["template_input_xpath"], timeout=10)
        inp.click()
        inp.send_keys(Keys.CONTROL, "a")
        inp.send_keys(name)
        time.sleep(0.25)
        inp.send_keys(Keys.ENTER)
        time.sleep(0.15)
        inp.send_keys(Keys.TAB)
        time.sleep(0.15)
        inp.send_keys(Keys.ESCAPE)
        time.sleep(0.25)

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
            el = self._wait_present_xpath(self.selectors["unit_input_xpath"], timeout=10)
        except Exception:
            el = self._wait_present_xpath(self.selectors["unit_input_fallback_xpath"], timeout=10)
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
        data = self._wait_present_xpath(self.selectors["date_from_xpath"], timeout=10)
        data_to = self._wait_present_xpath(self.selectors["date_to_xpath"], timeout=10)

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
        self._safe_click_xpath(self.selectors["run_button_xpath"], timeout=10, name="run_button")
        try:
            self._wait_present_css(self.selectors["spinner_waiting_css"], timeout=3)
        except Exception:
            pass

        self._wait_gone_css(self.selectors["spinner_waiting_css"], timeout=timeout)
        self._wait_present_css(self.selectors["results_table_css"], timeout=10)

    def expand_all_details(self, max_clicks: int = 25):
        """Развернуть детализацию"""
        for _ in range(max_clicks):
            icons = self.driver.find_elements(By.XPATH, self.selectors["expand_details_xpath"])
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
        table = self._wait_present_css(self.selectors["results_table_css"], timeout=10)
        rows = table.find_elements(By.CSS_SELECTOR, self.selectors["result_rows_css"])

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

        self.log(f"🎯 want_load={want_load!r}, want_unload={want_unload!r}")
        # 1. Собираем все посещения
        for tr in rows:
            tds = tr.find_elements(By.CSS_SELECTOR, self.selectors.get("row_cells_css", "td"))
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

            gf_raw = texts[gf_i]
            gf = self._norm(gf_raw)
            time_in = texts[in_i]
            time_out = texts[out_i]
            # self.log(f"GF raw={gf_raw!r} | norm={gf!r} | "f"load_match={self._zone_match(gf_raw, load_zone)} | "f"unload_match={self._zone_match(gf_raw, unload_zone)}")

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
            # same_zone_visits = [v for v in merged if v["gf"] == want_load]
            same_zone_visits = [v for v in merged if self._zone_match(v["gf"], want_load)]
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
            if not load_visit and want_load and self._zone_match(v["gf"], load_zone):
                load_visit = v
                res["load_in"] = v["in"]
                res["load_out"] = v["out"]
                continue

            if load_visit and want_unload and self._zone_match(v["gf"], unload_zone):
                if v["out_dt"] >= load_visit["in_dt"]:
                    res["unload_in"] = v["in"]
                    res["unload_out"] = v["out"]
                    break
        # self.log(f"VISITS={visits}")
        # self.log(f"MERGED={merged}")
        # self.log(f"RESULT={res}")
        return res

    def run_geo_report_for_trip(self, unit: str,
                                date_from: str, date_to: str,
                                load_zone: str, unload_zone: str,
                                template: str = "Crossing geozones") -> dict:
        self._ensure_on_wialon_tab()
        self._wait_page_settled(timeout=5)

        self.open_reports()
        self.select_template_by_typing(template)
        self.select_unit_by_typing(unit)
        self.set_interval(date_from, date_to)
        self.run_and_wait(timeout=75)
        self.expand_all_details()

        return self.extract_times(load_zone, unload_zone)

    # ---- Todo:для предчека переопределить чтоб не было дубля кода
    def _collect_merged_visits(self) -> list[dict]:
        """
        Общая заготовка:
        - читает таблицу отчёта
        - собирает посещения
        - фильтрует шум
        - склеивает дребезг
        Возвращает merged visits.
        """
        table = self._wait_present_css(self.selectors["results_table_css"], timeout=10)
        rows = table.find_elements(By.CSS_SELECTOR, self.selectors["result_rows_css"])

        dt_re = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\b")

        MIN_STAY_SECONDS = 120
        MERGE_GAP_SECONDS = 900

        def to_dt(s: str):
            try:
                return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
            except Exception:
                return None

        visits = []

        for tr in rows:
            tds = tr.find_elements(By.CSS_SELECTOR, self.selectors.get("row_cells_css", "td"))
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

            gf_raw = texts[gf_i]
            gf = self._norm(gf_raw)
            time_in = texts[in_i]
            time_out = texts[out_i]

            in_dt = to_dt(time_in)
            out_dt = to_dt(time_out)
            if not in_dt or not out_dt:
                continue

            stay_sec = int((out_dt - in_dt).total_seconds())
            if stay_sec < 0:
                continue

            visits.append({"gf_raw": gf_raw,
                           "gf": gf,
                           "in": time_in,
                           "out": time_out,
                           "in_dt": in_dt,
                           "out_dt": out_dt,
                           "stay_sec": stay_sec, })

        if not visits:
            self.log("VISITS=[]")
            return []

        filtered = []
        for v in visits:
            if v["stay_sec"] < MIN_STAY_SECONDS:
                self.log(f"⚠️ Игнорирую короткое посещение как шум: {v['gf']} {v['in']} -> {v['out']}")
                continue
            filtered.append(v)

        if not filtered:
            self.log("FILTERED=[]")
            return []

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

        # self.log(f"VISITS={visits}")
        # self.log(f"MERGED={merged}")
        return merged

    def extract_precheck_unload_state(self, unload_zone: str) -> dict:
        """
        Для быстрого precheck:
        ищем только выгрузку, без обязательного наличия погрузки.
        """
        want_unload = self._norm(unload_zone)
        self.log(f"🎯 PRECHECK want_unload={want_unload!r}")

        merged = self._collect_merged_visits()
        res = {"unload_in": "", "unload_out": ""}

        if not merged or not want_unload:
            # self.log(f"PRECHECK RESULT={res}")
            return res

        unload_visits = [v for v in merged if self._zone_match(v["gf"], want_unload)]
        if not unload_visits:
            # self.log(f"PRECHECK RESULT={res}")
            return res

        last_visit = unload_visits[-1]
        res["unload_in"] = last_visit["in"]
        res["unload_out"] = last_visit["out"]
        # self.log(f"PRECHECK RESULT={res}")
        return res

    def run_geo_report_precheck_unload(self, unit: str,
                                       date_from: str, date_to: str,
                                       unload_zone: str,
                                       template: str = "Пересечение гео") -> dict:
        self._ensure_on_wialon_tab()
        self._wait_page_settled(timeout=5)

        self.open_reports()
        self.select_template_by_typing(template)
        self.select_unit_by_typing(unit)
        self.set_interval(date_from, date_to)
        self.run_and_wait(timeout=75)
        self.expand_all_details()

        return self.extract_precheck_unload_state(unload_zone)
