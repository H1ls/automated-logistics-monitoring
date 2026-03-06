# LogistX\controllers\oneCRaceWriter.py
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pyautogui
import pydirectinput as pdi
import pyperclip
import pytesseract
from PIL import Image, ImageDraw

from LogistX.controllers.visionLocator import VisionLocator


class OneCRaceWriter:
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
        self.vision = VisionLocator(
            templates_dir=self.logistx_dir / "assets" / "onec_templates",
            threshold=float(vision_cfg.get("threshold", 0.82)),
            log_func=log_func
        )

        #  tmp тоже внутри LogistX
        self.tmp_dir = self.logistx_dir / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        pyautogui.FAILSAFE = True

    # ---------- small helpers ----------

    def _sleep(self, s=0.2):
        time.sleep(s)

    def _cancel_and_close(self):
        self.log("↩️ Отмена/закрытие (Esc x2)")
        # pyautogui.press("esc"); self._sleep(0.2)
        # pyautogui.press("esc"); self._sleep(0.2)

    def _paste_remote(self, text: str):
        pyperclip.copy(text)
        self._sleep(0.08)

        # 1) пытаемся вставить через pydirectinput (стабильнее в RDP)
        try:
            pdi.keyDown("ctrl")
            pdi.press("v")
            pdi.keyUp("ctrl")
            self._sleep(0.08)
            return
        except Exception:
            pass

        # 2) fallback на pyautogui ctrl+v
        try:
            pyautogui.keyDown("ctrl")
            pyautogui.press("v")
            pyautogui.keyUp("ctrl")
            self._sleep(0.08)
            return
        except Exception:
            pass

        # 3) ещё один fallback для RDP: Shift+Insert
        pyautogui.keyDown("shift")
        pyautogui.press("insert")
        pyautogui.keyUp("shift")
        self._sleep(0.08)

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

    def _press_ok(self):
        self.log("→ Сохранение (Ctrl+Enter)")
        pyautogui.hotkey("ctrl", "enter")
        self._sleep(0.9)

    def _goto_race_params(self) -> bool:
        # кнопка "Параметры рейса"
        return self._click_button("race_params")

    # _______________

    def _field_set_value(self, x: int, y: int, value: str):
        value = self._fmt_dt(value)
        self._sleep(0.05)
        pyautogui.click(x, y)
        self._sleep(0.08)
        pyautogui.press("f2")
        self._sleep(0.10)
        self._paste_remote(value)
        self._sleep(0.05)
        pyautogui.press("enter")



    def _copy_cell_text(self, x: int, y: int) -> str:
        # клик в ячейку
        pyautogui.click(x, y)
        self._sleep(0.08)

        # копируем (две попытки для RDP)
        try:
            pyperclip.copy("")
        except Exception:
            pass

        pyautogui.hotkey("ctrl", "c", interval=0.03)
        self._sleep(0.12)

        txt = ""
        try:
            txt = (pyperclip.paste() or "").strip()
        except Exception:
            txt = ""

        if not txt:
            pyautogui.hotkey("ctrl", "insert", interval=0.03)
            self._sleep(0.12)
            try:
                txt = (pyperclip.paste() or "").strip()
            except Exception:
                txt = ""

        return txt

    def debug_print(self, m_load, m_unload, x_arr, x_dep, offset_y, ts, shot_path, region):
        debug_points = []

        if m_load:
            y_load = m_load.center[1] + offset_y
            debug_points.append((x_arr, y_load, "LOAD arr_fact(click)"))
            debug_points.append((x_dep, y_load, "LOAD dep_fact(click)"))

        if m_unload:
            y_unload = m_unload.center[1] + offset_y
            debug_points.append((x_arr, y_unload, "UNLOAD arr_fact(click)"))
            debug_points.append((x_dep, y_unload, "UNLOAD dep_fact(click)"))

        dbg_path = self.tmp_dir / f"cargo_debug_{ts}.png"
        self._save_debug_overlay(shot_path, dbg_path, region=region, points=debug_points)

    def _calc_delay_minutes(self, fact: str, plan: str) -> int | None:
        """
        Возвращает:
          >0  — опоздал
          <0  — приехал раньше
          0   — ровно
          None — если не удалось распарсить
        """
        try:
            fmt = "%d.%m.%Y %H:%M"
            fact_dt = datetime.strptime(fact.strip()[:16], fmt)
            plan_dt = datetime.strptime(plan.strip()[:16], fmt)
            delta = fact_dt - plan_dt
            return int(delta.total_seconds() // 60)
        except Exception:
            return None

    def _parse_dt_1c(self, s: str) -> datetime | None:
        s = (s or "").strip()
        if not s:
            return None
        s = s[:16]  # "ДД.ММ.ГГГГ ЧЧ:ММ"
        try:
            return datetime.strptime(s, "%d.%m.%Y %H:%M")
        except Exception:
            return None

    def _calc_stay_minutes(self, start: str, end: str) -> int | None:
        a = self._parse_dt_1c(start)
        b = self._parse_dt_1c(end)
        if not a or not b:
            return None
        mins = int((b - a).total_seconds() // 60)
        if mins < 0:
            return None
        return mins

    def _round_hours_custom(self, total_minutes: int) -> int:
        hours = total_minutes // 60
        rem = total_minutes % 60
        if rem > 45:
            hours += 1
        return int(hours)

    def _calc_lateness_minutes(self, fact_arrive: str, deadline_arrive: str) -> int | None:
        """
        >0  опоздал на N минут (fact > deadline)
        <=0 вовремя/раньше (fact <= deadline) -> вернёт 0 или отрицательное
        """
        f = self._parse_dt_1c(fact_arrive)
        d = self._parse_dt_1c(deadline_arrive)
        if not f or not d:
            return None
        return int((f - d).total_seconds() // 60)

    def _lateness_text(self, mins: int) -> str:
        if mins > 0:
            return f"опоздал на {mins} мин"
        if mins < 0:
            return f"приехал раньше на {-mins} мин"
        return "приехал ровно в срок"

    def _format_hm(self, total_minutes: int | None) -> tuple[int, int]:
        if total_minutes is None:
            return 0, 0
        sign = -1 if total_minutes < 0 else 1
        total_minutes = abs(total_minutes)
        h = total_minutes // 60
        m = total_minutes % 60
        return h * sign, m

    def _ceil_hours_positive(self, total_minutes: int | None) -> int:
        """Опоздание: если минут >0 — считаем часы вверх (63 мин -> 2 ч)."""
        if total_minutes is None or total_minutes <= 0:
            return 0
        h = total_minutes // 60
        m = total_minutes % 60
        return int(h + (1 if m > 0 else 0))

    def _over_6h_hours(self, stay_hours: int) -> int:
        """Простой: из часов вычитаем 6ч, пишем только если результат > 1ч."""
        extra = max(0, int(stay_hours) - 6)
        return extra

    def _type_hours_value(self, hours: int):
        # формат: "(ХХ ч.)"
        text = f"({hours} ч.)"
        self._paste_remote(text)
        self._sleep(0.05)

    def _ctrl_f(self):
        # pydirectinput не имеет hotkey()
        try:
            pdi.keyDown("ctrl")
            pdi.press("f")
            pdi.keyUp("ctrl")
        except Exception:
            # fallback на pyautogui
            pyautogui.hotkey("ctrl", "f")
        self._sleep(0.2)

    def _add_nothing(self, text: str):
        if not self._click_insert_button():
            return False
        self._paste_remote(text)
        self._sleep(0.2)

    def _set_departure_dt(self, value: str):
        x, y = self.ui["fields"]["departure_dt"]
        self._field_set_value(x, y, value)

    def _click_departure_field_by_dx(self, dx: int) -> bool:
        cfg = self.ui.get("vision", {})
        region = tuple(cfg.get("race_params_region", [0, 0, 1920, 1080]))
        left, top, w, h = region

        tmp_dir = Path("LogistX/tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        shot = self.vision.screenshot(tmp_dir / "race_params.png", region=region)
        m = self.vision.find(shot, "lbl_departure.png", region_offset=(left, top))

        if not m:
            self.log("❌ Не нашёл лейбл 'Отправлен' (lbl_departure.png)")
            return False

        x = m.center[0] + int(dx)
        y = m.center[1]

        pyautogui.click(x, y)
        time.sleep(0.06)
        return True

    # ---------- steps ----------

    def _go_tab(self, tab_name: str) -> bool:
        # есть def _click_button
        rect = self.ui["tabs"].get(tab_name)
        if not rect:
            return False
        self.log(f"→ Вкладка: {tab_name}")
        self._click_rect(rect)
        self._sleep(0.5)
        return True

    def _fill_times_with_vision(self, payload: dict) -> bool:
        # region для поиска
        region = tuple(self.ui.get("vision", {}).get("search_region", [0, 0, 1920, 1080]))
        left, top, w, h = region

        # параметры
        vision_cfg = self.ui.get("vision", {})
        offset_x = int(vision_cfg.get("offset_x", 0))
        offset_y = int(vision_cfg.get("offset_y", 0))
        plan_dy = int(vision_cfg.get("plan_dy", 20))

        # storage
        self.last_plan_times = getattr(self, "last_plan_times", {})
        self.delay_info = getattr(self, "delay_info", {})

        # скрин
        ts = int(time.time() * 1000)
        shot_path = (self.tmp_dir / f"cargo_{ts}.png").resolve()
        self.vision.screenshot(shot_path, region=region)

        # 1) Находим X колонок по заголовкам
        m_arr = self.vision.find(shot_path, "hdr_arrival_fact.png", region_offset=(left, top))
        m_dep = self.vision.find(shot_path, "hdr_depart_fact.png", region_offset=(left, top))
        if not m_arr or not m_dep:
            self.log("❌ Не нашёл заголовки колонок 'Прибытие факт' / 'Убытие факт'")
            return False

        x_arr = m_arr.center[0] + offset_x
        x_dep = m_dep.center[0] + offset_x

        # 2) Находим строки по операциям
        m_load = self.vision.find(shot_path, "op_load.png", region_offset=(left, top))
        m_unload = self.vision.find(shot_path, "op_unload.png", region_offset=(left, top))

        # debug overlay (если у тебя debug_print уже принимает эти аргументы)
        try:
            self.debug_print(m_load, m_unload, x_arr, x_dep, offset_y, ts, shot_path, region)
        except Exception:
            pass

        ok_any = False

        # -------- Погрузка --------
        if m_load:
            y_load = m_load.center[1] + offset_y

            # ✅ deadline "до скольки мог приехать" берём ИЗ СТРОКИ НИЖЕ, В КОЛОНКЕ ПРИБЫТИЯ
            load_deadline = self._copy_cell_text(x_dep, y_load + plan_dy)
            self.last_plan_times["load_arrive_deadline"] = load_deadline

            # ✅ сравнение deadline vs фактическое прибытие
            fact_load_in = payload.get("load_in", "")
            mins = self._calc_lateness_minutes(fact_load_in, load_deadline)
            if mins is not None:
                self.delay_info["load_arrive"] = mins

            # ✅ заполнение факта
            if payload.get("load_in"):
                self._field_set_value(x_arr, y_load, payload["load_in"])

                ok_any = True
            if payload.get("load_out"):
                self._field_set_value(x_dep, y_load, payload["load_out"])
                ok_any = True
        else:
            self.log("⚠️ Не нашёл строку 'Погрузка'")

        # -------- Разгрузка --------
        if m_unload:
            y_unload = m_unload.center[1] + offset_y

            # ✅ deadline "до скольки мог приехать" берём ИЗ СТРОКИ НИЖЕ, В КОЛОНКЕ ПРИБЫТИЯ
            unload_deadline = self._copy_cell_text(x_dep, y_unload + plan_dy)
            self.last_plan_times["unload_arrive_deadline"] = unload_deadline

            # ✅ сравнение deadline vs фактическое прибытие
            fact_unload_in = payload.get("unload_in", "")
            mins = self._calc_lateness_minutes(fact_unload_in, unload_deadline)
            if mins is not None:
                self.delay_info["unload_arrive"] = mins

            # ✅ заполнение факта
            if payload.get("unload_in"):
                self._field_set_value(x_arr, y_unload, payload["unload_in"])
                self.log(f"SET unload_in  -> ({x_arr},{y_unload}) = {payload.get('unload_in')}")
                ok_any = True
            if payload.get("unload_out"):
                self._field_set_value(x_dep, y_unload, payload["unload_out"])
                self.log(f"SET unload_out -> ({x_dep},{y_unload}) = {payload.get('unload_out')}")
                ok_any = True
        else:
            self.log("⚠️ Не нашёл строку 'Разгрузка'")

        # ---- Опоздание ----
        load_late = self.delay_info.get("load_arrive")
        unload_late = self.delay_info.get("unload_arrive")

        load_h, load_m = self._format_hm(load_late)
        unload_h, unload_m = self._format_hm(unload_late)

        # ---- Простой ----
        mins_load = self._calc_stay_minutes(payload.get("load_in"), payload.get("load_out"))
        mins_unload = self._calc_stay_minutes(payload.get("unload_in"), payload.get("unload_out"))

        stay_load_h = self._round_hours_custom(mins_load) if mins_load is not None else 0
        stay_unload_h = self._round_hours_custom(mins_unload) if mins_unload is not None else 0

        result = {
            "ok": ok_any,

            "load_lateness": {
                "hours": load_h,
                "minutes": load_m,
                "total_minutes": load_late,
            },

            "unload_lateness": {
                "hours": unload_h,
                "minutes": unload_m,
                "total_minutes": unload_late,
            },

            "load_stay_hours": stay_load_h,
            "unload_stay_hours": stay_unload_h,
        }
        print(result)
        return result

    def _add_driver_deviation(self, text: str, hours: int):
        if not self._click_insert_button():
            return False

        # 1) Вводим "Вид"
        self._paste_remote(text)
        self._sleep(0.25)

        # 2) Завершаем редактирование ячейки "Вид"
        # F2 в 1С часто переключает режим редактирования/завершает ввод
        pdi.press("f2")
        self._sleep(0.15)

        # На всякий случай подтверждаем Enter (вне режима редактирования это "зафиксировать")
        pdi.press("enter")
        self._sleep(0.20)

        # 3) Переходим в колонку "Оценка водителя" (вправо надежнее, чем Tab в табличной части)
        pdi.press("right")
        self._sleep(0.15)
        pdi.press("enter")
        self._sleep(0.20)
        # Иногда нужно ещё раз вправо (если между ними есть колонка)
        # pyautogui.press("right"); self._sleep(0.10)

        # 4) Вводим часы
        self._paste_remote(f"{hours} ч.")
        self._sleep(0.20)

        # 5) Зафиксировать ввод
        pdi.press("enter")
        self._sleep(0.20)

        return True

    def _fill_driver_rating(self, calc: dict):
        """
        Логика по твоим правилам:
        1) Без отклонений — если нет опоздания (погр/выгр) и нет простоя >6ч (погр/выгр)
        2) Опоздание на погрузку — пишем часы
        3) Опоздание на разгрузку — пишем часы
        4) Простой на погрузке — (часы - 6), пишем если результат > 1ч
        5) Простой на разгрузке — (часы - 6), пишем если результат > 1ч
        """

        load_late_min = (calc.get("load_lateness") or {}).get("total_minutes")
        unload_late_min = (calc.get("unload_lateness") or {}).get("total_minutes")

        load_late_h = self._ceil_hours_positive(load_late_min)
        unload_late_h = self._ceil_hours_positive(unload_late_min)

        load_stay_h = int(calc.get("load_stay_hours") or 0)
        unload_stay_h = int(calc.get("unload_stay_hours") or 0)

        load_over6 = self._over_6h_hours(load_stay_h)
        unload_over6 = self._over_6h_hours(unload_stay_h)

        # писать простой только если > 1 часа после вычета 6ч
        write_load_over6 = load_over6 > 1
        write_unload_over6 = unload_over6 > 1

        has_any = (load_late_h > 0) or (unload_late_h > 0) or write_load_over6 or write_unload_over6

        if not has_any:
            # 1) Без отклонений: down 1 + enter
            self.log("🟩 Оценка водителя: Без отклонений")
            self._add_nothing("Без отклонений")
            return

        if load_late_h > 0:
            self.log(f'Опоздание на погрузку",{load_late_h}')
            self._add_driver_deviation("Опоздание на погрузку", load_late_h)

        if unload_late_h > 0:
            self.log(f'Опоздание на разгрузку",{unload_late_h}')
            self._add_driver_deviation("Опоздание на разгрузку", unload_late_h)

        if write_load_over6:
            self.log(f'Простой на погрузке",{load_over6}')
            self._add_driver_deviation("Простой на погрузке", load_over6)

        if write_unload_over6:
            self.log(f'Простой на разгрузке",{unload_over6}')
            self._add_driver_deviation("Простой на разгрузке", unload_over6)

    def _click_insert_button(self) -> bool:
        region = tuple(self.ui["vision"]["rating_region"])
        left, top, w, h = region

        import time
        ts = int(time.time() * 1000)
        shot_path = (self.tmp_dir / f"rating_{ts}.png").resolve()

        self.vision.screenshot(shot_path, region=region)

        m = self.vision.find(shot_path, "btn_insert.png", region_offset=(left, top))
        if not m:
            self.log("❌ Не нашёл кнопку INS")
            return False

        x, y = m.center
        pyautogui.click(x, y)
        self._sleep(0.5)
        return True

    def _save_debug_overlay(self, src_path: Path, out_path: Path, region, points: list[tuple[int, int, str]]):
        """
        src_path: путь к исходному скрину (который сделан по region)
        out_path: куда сохранить debug-версию
        region: (left, top, width, height) — та же область, что использовали в screenshot()
        points: список точек на ЭКРАНЕ (x,y) + label
        """
        left, top, w, h = region
        img = Image.open(src_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        for x, y, label in points:
            # переводим координаты экрана -> координаты внутри region-снимка
            rx = x - left
            ry = y - top

            # квадрат 16x16 + крестик
            r = 10
            draw.rectangle([rx - r, ry - r, rx + r, ry + r], outline=(255, 0, 0), width=2)
            draw.line([rx - r, ry, rx + r, ry], fill=(255, 0, 0), width=2)
            draw.line([rx, ry - r, rx, ry + r], fill=(255, 0, 0), width=2)

            # подпись рядом
            draw.text((rx + r + 4, ry - r - 2), label, fill=(255, 0, 0))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        self.log(f"🧩 Debug overlay saved: {out_path} (marks={len(points)})")

    def _fmt_dt(self, s: str) -> str:
        """
        Приводим к формату 1С: 'ДД.ММ.ГГГГ ЧЧ:ММ' (без секунд).
        Если секунд нет — оставляем как есть.
        """
        s = (s or "").strip()
        if not s:
            return s
        # 20.02.2026 04:21:13 -> 20.02.2026 04:21
        if len(s) >= 16 and s.count(":") >= 2:
            return s[:16]
        return s

    # ---------- main ----------
    def fill_race(self, payload: dict) -> bool:
        if not self.rdp_activator():
            self.log("❌ RDP не активирован")
            return False

        try:
            # вкладка Грузы (координаты)
            if not self._go_tab("cargo"):
                self.log("❌ Не смог перейти на вкладку Грузы")
                self._cancel_and_close()
                return False

            # ✅ заполняем времена (mock) через OpenCV
            calc = self._fill_times_with_vision(payload)
            if not calc or not calc.get("ok"):
                self.log("❌ Не смог заполнить времена (vision)")
                self._cancel_and_close()
                return False
            self.last_calc = calc  # сохраним на всякий

            # Основные данные (вкладка)
            if not self._go_tab("main"):
                self.log("❌ Не смог перейти на Основные данные")
                self._cancel_and_close()
                return False
            # Оценка водителя (кнопка)
            if not self._click_button("driver_rating"):
                self.log("❌ Не смог открыть Оценка водителя")
                self._cancel_and_close()
                return False

            # Оценка водителя (кнопка)
            if not self._click_button("driver_rating"):
                self.log("❌ Не смог открыть Оценка водителя")
                self._cancel_and_close()
                return False
            # Ввод Оценка водителя
            self._fill_driver_rating(self.last_calc)
            # TODO: дата закрытия рейса (так же через vision по шаблону поля)
            # OK (подберем точный хоткей под твою 1С)
            # self._press_ok()
            self.log(f"✅ Рейс заполнен")
            return True
        except Exception as e:
            self.log(f"OneCRaceWriter ❌ Exception: {e}")
            self._cancel_and_close()
            return False
