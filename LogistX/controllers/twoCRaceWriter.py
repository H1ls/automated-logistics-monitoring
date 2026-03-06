# LogistX\controllerst\woCRaceWriter
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pyautogui
import pydirectinput as pdi
import pyperclip
import pytesseract
from PIL import Image, ImageDraw

from LogistX.controllers.visionLocator import VisionLocator


class TwoCRaceWriter:
    def __init__(self, rdp_activator, log_func=print, ui_map_path=None):
        self.log = log_func
        self.rdp_activator = rdp_activator
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        #  базовая папка: .../LogistX
        self.logistx_dir = Path(__file__).resolve().parents[1]

        #  ui map по умолчанию
        if ui_map_path is None:
            ui_map_path = self.logistx_dir / "config" / "onec_ui_map.json"
        else:
            ui_map_path = Path(ui_map_path)
            if not ui_map_path.is_absolute():
                ui_map_path = self.logistx_dir / ui_map_path

        self.ui = json.loads(ui_map_path.read_text(encoding="utf-8"))

        vision_cfg = self.ui.get("vision", {})
        self.vision = VisionLocator(templates_dir=self.logistx_dir / "assets" / "onec_templates",
                                    threshold=float(vision_cfg.get("threshold", 0.82)),
                                    log_func=log_func)

        #  tmp тоже внутри LogistX
        self.tmp_dir = self.logistx_dir / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        self.debug_force_departure = True  # включить подробный трейс
        self.debug_force_sleep = 0.35  # базовая пауза между шагами (сек)
        self.debug_force_screens = True  # сохранять скрины
        pyautogui.FAILSAFE = True

    # ---------- small helpers ----------
    def _sleep(self, s=0.2):
        time.sleep(s)

    def _cancel_and_close(self):
        self.log("↩️ Отмена/закрытие (Esc x2)")
        pyautogui.press("esc")
        self._sleep(0.2)
        # pyautogui.press("esc"); self._sleep(0.2)

    def _paste_remote(self, text: str):
        pyperclip.copy(text)
        self._sleep(0.08)
        try:
            pdi.keyDown("ctrl")
            pdi.press("v")
            pdi.keyUp("ctrl")
            self._sleep(0.08)
            return
        except Exception:
            pyautogui.hotkey("ctrl", "v")

    def _click_rect(self, rect):
        x1, y1, x2, y2 = rect
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        pyautogui.click(cx, cy)
        self._sleep(0.15)

    def _click_button(self, btn_name: str) -> bool:
        rect = self.ui["buttons"].get(btn_name)
        if not rect:
            return False
        self.log(f"→ Кнопка: {btn_name}")
        self._click_rect(rect)
        self._sleep(0.4)
        return True

    def _goto_race_params(self) -> bool:
        # кнопка "Параметры рейса"
        return self._click_button("race_params")

    def _press_ok(self):
        self.log("→ Сохранение (Ctrl+Enter)")
        pyautogui.hotkey("ctrl", "enter")
        self._sleep(0.9)

    def _click_menu_open(self) -> bool:
        # скрин маленькой области вокруг меню (примерно)
        region = (175, 270, 765, 800)  # подстроим потом
        left, top, w, h = region

        ts = int(time.time() * 1000)
        shot_path = (self.tmp_dir / f"menu_{ts}.png").resolve()
        try:
            self.vision.screenshot(shot_path, region=region)
            m = self.vision.find(shot_path, "menu_open.png", region_offset=(left, top))
            if not m:
                self.log("❌ Не нашёл пункт меню 'Открыть'")
                return False

            x, y = m.center
            pyautogui.click(x, y)
            self._sleep(1.2)
            return True
        finally:
            try:
                if shot_path.exists():
                    shot_path.unlink()
            except Exception:
                pass

    def _ctrl_f(self):
        try:
            pdi.keyDown("ctrl")
            pdi.press("f")
            pdi.keyUp("ctrl")
        except Exception:
            # fallback на pyautogui
            pyautogui.hotkey("ctrl", "f")
        self._sleep(0.2)

    def _type_into_current_field(self, value: str):
        pyautogui.hotkey("ctrl", "a", interval=0.03)
        self._sleep(0.03)
        self._paste_remote(value)
        self._sleep(0.05)
        pyautogui.press("tab")
        self._sleep(0.10)

    def _close_error_dialog(self):
        # чаще всего ОК = Enter
        self._sleep(0.2)
        pdi.press("enter")
        self._sleep(0.2)

    # ____________
    def _open_race_from_list(self, race_no: str) -> bool:
        pyautogui.click(500, 500)
        self.log(f"→ Открываю рейс из списка: {race_no}")

        self._ctrl_f()
        self._sleep(0.2)

        self._paste_remote(race_no)
        pdi.press("enter")
        self._sleep(0.2)

        pdi.press("enter")
        self._sleep(1)
        ok = self._click_menu_open()
        return ok

    def _type_into_current_field_commit_enter(self, value: str):
        pyautogui.hotkey("ctrl", "a", interval=0.03)
        self._sleep(0.03)
        self._paste_remote(value)
        self._sleep(0.05)
        pyautogui.press("enter")
        self._sleep(0.10)

    def _wait_error_dialog(self, timeout: float = 2.0, poll: float = 0.15) -> datetime | None:
        t0 = time.time()
        saw_dialog = False
        while time.time() - t0 <= timeout:
            if self._is_error_dialog_present():
                saw_dialog = True
                dt = self._extract_finish_dt_from_error()
                if dt is not None:
                    return dt
            time.sleep(poll)

        if saw_dialog:
            self.log("⚠️ Окно ошибки было, но OCR не извлёк 'выполнен'")
            # cfg = self.ui.get("vision", {})
            # region = tuple(cfg.get("error_search_region", [0, 0, 1920, 1080]))
            # self.vision.screenshot(self.tmp_dir / "debug_err_full.png", region=region)
            # region_text = tuple(cfg.get("error_text_region", [570, 460, 780, 120]))
            # self.vision.screenshot(self.tmp_dir / "debug_err_text.png", region=region_text)
        return None

    def _wait_open_race(self, timeout: float = 1.5, poll: float = 0.15):
        t0 = time.time()
        while time.time() - t0 <= timeout:
            m = self._find_departure_label()
            if m is not None:
                return m
            time.sleep(poll)
        return None

    def _dismiss_error_and_get_finish_dt(self, timeout=1.0, poll=0.1) -> datetime | None:
        """
        Если окно ошибки появилось — читает max 'выполнен' через OCR и закрывает.
        Возвращает datetime (max выполнен) или None если ошибки нет.
        """
        t0 = time.time()
        while time.time() - t0 <= timeout:
            if self._is_error_dialog_present():
                dt = self._extract_finish_dt_from_error()  # <-- главное отличие
                self._close_error_dialog()
                return dt

            time.sleep(poll)
        return None

    def _is_error_dialog_present(self) -> bool:
        cfg = self.ui.get("vision", {})
        region = tuple(cfg.get("error_search_region", [0, 0, 1920, 1080]))
        left, top, w, h = region
        shot = self.vision.screenshot(self.tmp_dir / "err_probe.png", region=region)
        m = self.vision.find(shot, "error_data.png", region_offset=(left, top))
        return m  # Match | None

    def _find_departure_label(self):
        """Поиск координат ячейки Отправки рейса Дата / Время"""
        cfg = self.ui.get("vision", {})
        region = tuple(cfg.get("lbl_departure", [0, 0, 1920, 1080]))
        left, top, w, h = region

        tmp_dir = self.tmp_dir
        tmp_dir.mkdir(parents=True, exist_ok=True)

        shot = self.vision.screenshot(tmp_dir / "lbl_departure.png", region=region)
        m = self.vision.find(shot, "lbl_departure.png", region_offset=(left, top))
        if not m:
            self.log("❌ Не нашёл лейбл 'Отправлен' (lbl_departure.png)")
        return m

    @staticmethod
    def xyxy_to_region(x1, y1, x2, y2):
        return (x1, y1, x2 - x1, y2 - y1)

    def _extract_finish_dt_from_error(self) -> datetime | None:
        """
        Скрин error_text_region и извлекает datetime, относящийся к 'выполнен'.
        Устойчиво к строке вида:
          ... отправлен 22.02.2026 17:12:00 выполнен 25.02.2026 19:14:00 ответственный: ...
        Берём дату ПОСЛЕ слова 'выполнен' (желательно до 'ответственный'), затем max().
        """
        cfg = self.ui.get("vision", {})
        region = self.xyxy_to_region(560, 450, 1360, 580)
        # region = tuple(cfg.get("error_text_region", [570, 460, 780, 120]))

        img_path = self.tmp_dir / "err_data_text.png"
        img = pyautogui.screenshot(region=region)
        img.save(img_path)

        with Image.open(img_path) as pil:
            text = pytesseract.image_to_string(pil, lang="rus")

        norm = " ".join(text.split())
        low = norm.lower()
        # self.log(f"OCR: {norm}")
        dt_re = r"\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}:\d{2}"

        # 1) лучший путь: кусок после 'выполнен' до 'ответственн'
        # (ответственный/ответств./ответственн — OCR может резать окончания)
        m = re.search(r"выполнен\s+(.*?)(?:ответственн|$)", low, flags=re.IGNORECASE)
        if m:
            tail = m.group(1)
            found = re.findall(dt_re, tail)
            dts = []
            for s in found:
                try:
                    dts.append(datetime.strptime(s, "%d.%m.%Y %H:%M:%S"))
                except Exception:
                    pass
            if dts:
                best = max(dts)
                self.log(f"{best.strftime('%d.%m.%Y %H:%M:%S')} выполнен (max)")
                return best

        # 2) если 'ответственный' не поймался — берём первый datetime сразу после 'выполнен'
        m = re.search(r"выполнен\s+(" + dt_re + r")", low, flags=re.IGNORECASE)
        if m:
            s = m.group(1)
            try:
                best = datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
                self.log(f"{best.strftime('%d.%m.%Y %H:%M:%S')} выполнен (max)")
                return best
            except Exception:
                pass

        # 3) fallback: оба формата (на случай другого текста)
        matches = []
        matches += re.findall(r"выполнен\s+(" + dt_re + r")", low, flags=re.IGNORECASE)
        matches += re.findall(r"(" + dt_re + r")\s+выполнен", low, flags=re.IGNORECASE)

        dts = []
        for s in matches:
            try:
                dts.append(datetime.strptime(s, "%d.%m.%Y %H:%M:%S"))
            except Exception:
                pass

        if not dts:
            return None

        best = max(dts)
        self.log(f"{best.strftime('%d.%m.%Y %H:%M:%S')} выполнен (max)")
        return best

    def probe_departure_finish_dt(self, current_departure: str, max_attempts: int = 4) -> datetime | None:
        """
        1) Вводим ТОЛЬКО дату (без времени) специально, чтобы выскочила ошибка.
        2) Если ошибки нет — минус 1 день и повтор (до max_attempts).
        3) Не уходим раньше load_in - 2 дня.
        4) Если в итоге ошибки нет — возвращаем None.
        """
        last_cand: datetime | None = None
        base = datetime.strptime(current_departure, "%d.%m.%Y %H:%M")

        m = self._wait_open_race(timeout=2)
        if not m:
            return None

        for attempt in range(1, max_attempts + 1):
            cand = base - timedelta(days=(attempt - 1))  # 0, -1, -2, -3
            last_cand = cand

            dx_day = int(self.ui.get("vision", {}).get("departure_day_dx", 80))
            # клик в поле ДАТЫ
            pyautogui.click(m.center[0] + dx_day, m.center[1])
            self._sleep(0.06)

            # вводим ТОЛЬКО дату
            date_str = cand.strftime("%d.%m.%Y")
            self.log(f"🧪 Probe attempt {attempt}: ставлю дату {date_str} (время не трогаю)")
            self._type_into_current_field_commit_enter(date_str)
            # ждём/проверяем ошибку (OCR)
            finish_dt = self._wait_error_dialog(timeout=2)
            if finish_dt:
                self.log(f"✅ Ошибка поймана, выполнен={finish_dt:%d.%m.%Y %H:%M:%S}")
                self._close_error_dialog()
                return finish_dt

            self.log("ℹ️ Ошибки нет — пробую дату ещё на день раньше")

        # fallback: берём последнюю дату, которую пробовали
        if last_cand:
            fd = last_cand.replace(hour=0, minute=0, second=0, microsecond=0)
            self.log(f"⚠️ За {max_attempts} попытки ошибка не появилась — беру fallback fd={fd:%d.%m.%Y %H:%M}")
            return fd
        return None

    # def force_set_departure_datetime(self, dt_to_set: datetime, rounds: int = 6) -> bool:
    #     if not self._goto_race_params():
    #         return False
    #     self._sleep(0.15)
    #
    #     m = self._find_departure_label()
    #     if not m:
    #         return False
    #
    #     cfg = self.ui.get("vision", {})
    #     dx_day = int(cfg.get("departure_day_dx", 80))
    #     dx_time = int(cfg.get("departure_time_dx", 200))
    #
    #     target = dt_to_set + timedelta(minutes=1)
    #
    #     for i in range(1, rounds + 1):
    #         date_str = target.strftime("%d.%m.%Y")
    #         time_str = target.strftime("%H:%M")
    #         self.log(f"🔧 Fix round {i}: ставлю {date_str} {time_str}")
    #
    #         # 1) Время
    #         pyautogui.click(m.center[0] + dx_time, m.center[1])
    #         self._sleep(0.05)
    #         self._type_into_current_field(time_str)
    #
    #         dt_err = self._dismiss_error_and_get_finish_dt(timeout=1.0, poll=0.1)
    #         if dt_err and dt_err >= target:
    #             target = dt_err + timedelta(minutes=1)
    #             self.log(f"↗️ target обновлён по ошибке (после времени): {target:%d.%m.%Y %H:%M}")
    #             continue
    #
    #         # 2) Дата
    #         pyautogui.click(m.center[0] + dx_day, m.center[1])
    #         self._sleep(0.05)
    #         self._type_into_current_field(date_str)
    #
    #         dt_err = self._dismiss_error_and_get_finish_dt(timeout=1.0, poll=0.1)
    #         if dt_err and dt_err >= target:
    #             target = dt_err + timedelta(minutes=1)
    #             self.log(f"↗️ target обновлён по ошибке (после даты): {target:%d.%m.%Y %H:%M}")
    #             continue
    #
    #         # 3) Контроль: ошибок больше нет
    #         dt_err = self._dismiss_error_and_get_finish_dt(timeout=0.6, poll=0.1)
    #         if not dt_err:
    #             return target
    #
    #         target = dt_err + timedelta(minutes=1)
    #         self.log(f"↗️ Ошибка контроля, target={target:%d.%m.%Y %H:%M}")
    #
    #     return False

    def force_set_departure_datetime(self, dt_base: datetime, rounds: int = 6) -> datetime | None:
        """Ввод уже полученного времени в два захода.
            Получения новго времени если полученное dt_base не верное """

        # self._trace_step("start", dt_base=dt_base)

        if not self._goto_race_params():
            # self._trace_step("fail_goto_race_params")
            return None

        # self._step_sleep(1.0)
        m = self._find_departure_label()
        # self._trace_step("find_label", found=bool(m), center=(getattr(m, "center", None)))
        if not m:
            # self._debug_screen("no_lbl_departure")  # на всякий
            return None

        cfg = self.ui.get("vision", {})
        dx_day = int(cfg.get("departure_day_dx", 80))
        dx_time = int(cfg.get("departure_time_dx", 200))

        target = dt_base + timedelta(minutes=1)
        # self._trace_step("init_target", target=target, dx_day=dx_day, dx_time=dx_time)

        # self._debug_screen("before_any")

        for i in range(1, rounds + 1):
            date_str = target.strftime("%d.%m.%Y")
            time_str = target.strftime("%H:%M")

            # self._trace_step("round_begin", round=i, target=target, date_str=date_str, time_str=time_str)

            # ---------- TIME ----------
            x_time = m.center[0] + dx_time
            y = m.center[1]
            # self._trace_step("click_time", x=x_time, y=y)
            pyautogui.click(x_time, y)
            # self._step_sleep(0.6)

            # self._trace_step("type_time", time_str=time_str)
            self._type_into_current_field(time_str)
            # self._step_sleep(0.8)

            dt_err = self._dismiss_error_and_get_finish_dt(timeout=1.2, poll=0.1)
            # self._trace_step("after_time", dt_err=dt_err)

            if dt_err:
                # скрин после появления ошибки
                # self._debug_screen(f"err_after_time_r{i}")
                if dt_err >= target:
                    old = target
                    target = dt_err + timedelta(minutes=1)
                    # self._trace_step("target_bump_after_time", old=old, dt_err=dt_err, new=target)
                    # self._step_sleep(1.0)
                    continue

            # ---------- DATE ----------
            x_day = m.center[0] + dx_day
            # self._trace_step("click_date", x=x_day, y=y)
            pyautogui.click(x_day, y)
            # self._step_sleep(0.6)

            # self._trace_step("type_date", date_str=date_str)
            self._type_into_current_field(date_str)
            # self._step_sleep(0.8)

            dt_err = self._dismiss_error_and_get_finish_dt(timeout=1.2, poll=0.1)
            # self._trace_step("after_date", dt_err=dt_err)

            if dt_err:
                # self._debug_screen(f"err_after_date_r{i}")
                if dt_err >= target:
                    old = target
                    target = dt_err + timedelta(minutes=1)
                    # self._trace_step("target_bump_after_date", old=old, dt_err=dt_err, new=target)
                    # self._step_sleep(1.0)
                    continue

            # ---------- CONTROL ----------
            dt_err = self._dismiss_error_and_get_finish_dt(timeout=0.8, poll=0.1)
            # self._trace_step("control", dt_err=dt_err)

            if not dt_err:
                # self._trace_step("success", final_target=target)
                # self._debug_screen(f"success_r{i}")
                return target

            old = target
            target = dt_err + timedelta(minutes=1)
            # self._trace_step("target_bump_control", old=old, dt_err=dt_err, new=target)
            # self._debug_screen(f"err_control_r{i}")
            # self._step_sleep(1.0)

        # self._trace_step("fail_rounds_exceeded", last_target=target)
        # self._debug_screen("fail_rounds_exceeded")
        return None

    # ------- main -----
    def open_race_and_read_departure_dt(self, race_no: str) -> datetime | None:
        """
        1) Активируем RDP
        2) Открываем рейс (поиск ctrl+f, enter, "Открыть")
        3) Заходим в "Параметры рейса"
        4) Находим lbl_departure и копируем значение поля даты/времени
        5) race_no Пример:"Рейс (уэ) ВТ000001946 от 25.02.2026 16:24:23"
        """
        if not self.rdp_activator():
            self.log("❌ RDP не активирован")
            return None
        if not self._open_race_from_list(race_no):
            self.log(f"❌ Не открылся рейс {race_no}")
            return None

        try:
            time_rc = race_no.split(" от ", 1)[1][:-3]
            base_fd = self.probe_departure_finish_dt(time_rc)
            if not base_fd:
                self.log("❌ Не удалось получить выполнен/max — не меняю дату")
                return None

            actual = self.force_set_departure_datetime(base_fd)
            if not actual:
                self.log("❌ Не удалось выставить дату отправления (force_set...)")
                return None

            self.log(f"✅ Дата отправления выставлена: {actual:%d.%m.%Y %H:%M}")
            return actual

        except Exception as e:
            self.log(f"❌ TwoCRaceWriter Exception: {e}")
            self._cancel_and_close()
            return None

    def _debug_departure_dx_points(self, m, region, dx_day: int, dx_time: int, name_prefix: str = "dep_dx"):
        """
        Рисует куда кликаем по dx_day/dx_time относительно найденного lbl_departure.
        region: (left, top, w, h) — та же область, где делали screenshot/поиск.
        m: Match (из VisionLocator) с .center в координатах ЭКРАНА.
        """
        left, top, w, h = region

        ts = int(time.time() * 1000)
        shot_path = (self.tmp_dir / f"{name_prefix}_{ts}.png").resolve()

        # 1) делаем скрин той же области
        self.vision.screenshot(shot_path, region=region)

        # 2) рисуем точки
        img = Image.open(shot_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        def draw_point(screen_x: int, screen_y: int, label: str):
            # переводим экранные координаты в координаты внутри region-снимка
            x = screen_x - left
            y = screen_y - top
            r = 10
            draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 0, 0), width=3)
            draw.line([x - r, y, x + r, y], fill=(255, 0, 0), width=2)
            draw.line([x, y - r, x, y + r], fill=(255, 0, 0), width=2)
            draw.text((x + r + 6, y - r - 2), label, fill=(255, 0, 0))

        # базовая точка — центр лейбла
        base_x, base_y = m.center

        # куда кликаем
        x_day, y_day = base_x + int(dx_day), base_y
        x_time, y_time = base_x + int(dx_time), base_y

        draw_point(base_x, base_y, "LBL center")
        draw_point(x_day, y_day, f"DATE dx_day={dx_day}")
        draw_point(x_time, y_time, f"TIME dx_time={dx_time}")

        img.save(shot_path)
        self.log(f"🧩 Debug dx overlay saved: {shot_path}")

    def _step_sleep(self, mult: float = 1.0):
        s = float(getattr(self, "debug_force_sleep", 0.0) or 0.0)
        if s > 0:
            time.sleep(s * mult)

    def _trace_step(self, tag: str, **kv):
        """Единый формат лога для force_set_departure_datetime."""
        if not getattr(self, "debug_force_departure", False):
            return
        parts = [f"{k}={v}" for k, v in kv.items()]
        self.log(f"🧭 force_departure | {tag}" + ((" | " + " ".join(parts)) if parts else ""))

    def _debug_screen(self, name: str, region=None):
        if not getattr(self, "debug_force_screens", False):
            return None
        ts = int(time.time() * 1000)
        path = (self.tmp_dir / f"force_departure_{ts}_{name}.png").resolve()
        try:
            self.vision.screenshot(path, region=region)
            return str(path)
        except:
            # except Exception as e:
            # self._trace_step("screen_fail", name=name, err=repr(e))
            return None
