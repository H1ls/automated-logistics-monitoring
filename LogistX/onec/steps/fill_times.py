# LogistX/onec/steps/fill_times.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw


class FillTimesStep:
    stage = "fill_times"

    def __init__(self, session, errors, log_func=print, debug_mode: bool = True):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.debug_mode = debug_mode

    @staticmethod
    def _fmt_dt_1c(value: str | None) -> str:
        value = (value or "").strip()
        return value[:16] if len(value) >= 16 else value

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        value = (value or "").strip()
        if not value: return None

        candidates = [value[:19],  # dd.mm.yyyy HH:MM:SS
                      value[:16], ]  # dd.mm.yyyy HH:MM

        for item in candidates:
            for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
                try:
                    return datetime.strptime(item, fmt)
                except ValueError:
                    pass
        return None

    def _calc_lateness_minutes(self, fact_arrive: str | None, deadline_arrive: str | None) -> int | None:
        fact_dt = self._parse_dt(fact_arrive)
        deadline_dt = self._parse_dt(deadline_arrive)
        if not fact_dt or not deadline_dt:
            return None

        minutes = int((fact_dt - deadline_dt).total_seconds() // 60)
        return max(0, minutes)

    def _calc_stay_minutes(self, arrive_dt: str | None, depart_dt: str | None) -> int | None:
        arrive = self._parse_dt(arrive_dt)
        depart = self._parse_dt(depart_dt)
        if not arrive or not depart:
            return None

        minutes = int((depart - arrive).total_seconds() // 60)
        if minutes < 0:
            return None
        return minutes

    @staticmethod
    def _ceil_hours_positive(total_minutes: int | None) -> int:
        if total_minutes is None or total_minutes <= 0:
            return 0
        hours = total_minutes // 60
        rem = total_minutes % 60
        if rem > 0:
            hours += 1
        return int(hours)

    @staticmethod
    def _round_hours_custom(total_minutes: int | None) -> int:
        """
        Для простоя:
        - до 45 минут остатка не округляем вверх
        - > 45 минут округляем вверх
        """
        if total_minutes is None or total_minutes <= 0:
            return 0

        hours = total_minutes // 60
        rem = total_minutes % 60
        if rem > 45:
            hours += 1
        return int(hours)

    @staticmethod
    def _over_6h_hours(stay_hours: int) -> int:
        return max(0, int(stay_hours) - 6)

    def _ensure_calc_state(self, ctx) -> dict:
        if not hasattr(ctx, "state") or ctx.state is None:
            ctx.state = {}
        calc = ctx.state.get("calc")
        if not isinstance(calc, dict):
            calc = {}
            ctx.state["calc"] = calc
        return calc

    def _draw_debug_points(self, shot_path: str | Path, points: list[tuple[str, int, int]]):
        if not self.debug_mode:
            return

        dbg_path = Path(shot_path).with_name(Path(shot_path).stem + "_debug.png")

        with Image.open(shot_path).convert("RGB") as img:
            draw = ImageDraw.Draw(img)

            left, top, _, _ = self.session.ui_map.get_region("cargo_search_region")

            for label, x_abs, y_abs in points:
                x = x_abs - left
                y = y_abs - top

                r = 8
                draw.ellipse((x - r, y - r, x + r, y + r), outline="red", width=3)
                draw.text((x + 10, y - 10), label, fill="red")

            img.save(dbg_path)

        self.log(f"🧪 debug screenshot: {dbg_path}")

    def _copy_deadline(self, x_dep: int, y_row: int, plan_dy: int, label: str) -> str:
        x = x_dep
        y = y_row + plan_dy
        text = self.session.copy_cell_text(x, y)
        self.log(f"📋 {label}: copy deadline from ({x}, {y}) -> {text!r}")
        return text

    def _set_cell(self, x: int, y: int, value: str, label: str):
        value = self._fmt_dt_1c(value)
        self.log(f"📝 {label}: {value} -> ({x}, {y})")
        self.session.replace_cell(x, y, value, submit=True)
        self.session.sleep(0.25)

        err = self.errors.detect()
        if err:
            self.errors.close_error_dialog()
            raise RuntimeError(f"Ошибка при заполнении {label}: {err.kind}")

    def _store_calc(self, ctx):
        calc = self._ensure_calc_state(ctx)

        load_lateness_minutes = self._calc_lateness_minutes(ctx.load_in, getattr(ctx, "load_arrive_deadline", None))
        unload_lateness_minutes = self._calc_lateness_minutes(ctx.unload_in,
                                                              getattr(ctx, "unload_arrive_deadline", None))

        load_stay_minutes = self._calc_stay_minutes(ctx.load_in, ctx.load_out)
        unload_stay_minutes = self._calc_stay_minutes(ctx.unload_in, ctx.unload_out)

        load_late_hours = self._ceil_hours_positive(load_lateness_minutes)
        unload_late_hours = self._ceil_hours_positive(unload_lateness_minutes)

        load_stay_hours = self._round_hours_custom(load_stay_minutes)
        unload_stay_hours = self._round_hours_custom(unload_stay_minutes)

        load_over_6h_hours = self._over_6h_hours(load_stay_hours)
        unload_over_6h_hours = self._over_6h_hours(unload_stay_hours)

        calc.update({"load_arrive_deadline": getattr(ctx, "load_arrive_deadline", None),
                     "unload_arrive_deadline": getattr(ctx, "unload_arrive_deadline", None),

                     "load_lateness_minutes": load_lateness_minutes,
                     "unload_lateness_minutes": unload_lateness_minutes,

                     "load_late_hours": load_late_hours,
                     "unload_late_hours": unload_late_hours,

                     "load_stay_minutes": load_stay_minutes,
                     "unload_stay_minutes": unload_stay_minutes,

                     "load_stay_hours": load_stay_hours,
                     "unload_stay_hours": unload_stay_hours,

                     "load_over_6h_hours": load_over_6h_hours,
                     "unload_over_6h_hours": unload_over_6h_hours, })

        driver_rating_items = []

        if load_late_hours > 0:
            driver_rating_items.append({"kind": "Опоздание на погрузку",
                                        "hours": load_late_hours, })

        if unload_late_hours > 0:
            driver_rating_items.append({"kind": "Опоздание на разгрузку",
                                        "hours": unload_late_hours, })

        if load_over_6h_hours > 1:
            driver_rating_items.append({"kind": "Простой на погрузке",
                                        "hours": load_over_6h_hours, })

        if unload_over_6h_hours > 1:
            driver_rating_items.append({"kind": "Простой на разгрузке",
                                        "hours": unload_over_6h_hours, })

        calc["driver_rating_items"] = driver_rating_items

        self.log("📊 calc: "
                 f"load_deadline={calc['load_arrive_deadline']!r}, "
                 f"unload_deadline={calc['unload_arrive_deadline']!r}, "
                 f"load_lateness_minutes={load_lateness_minutes}, "
                 f"unload_lateness_minutes={unload_lateness_minutes}, "
                 f"load_stay_minutes={load_stay_minutes}, "
                 f"unload_stay_minutes={unload_stay_minutes}, "
                 f"load_late_hours={load_late_hours}, "
                 f"unload_late_hours={unload_late_hours}, "
                 f"load_stay_hours={load_stay_hours}, "
                 f"unload_stay_hours={unload_stay_hours}, "
                 f"load_over_6h_hours={load_over_6h_hours}, "
                 f"unload_over_6h_hours={unload_over_6h_hours}"
                 )

        if driver_rating_items:
            self.log(f"🧾 driver_rating_items={driver_rating_items}")
        else:
            self.log("🧾 driver_rating_items=[] -> Без отклонений")

    def run(self, ctx):
        has_any = any([ctx.load_in, ctx.load_out, ctx.unload_in, ctx.unload_out])
        if not has_any:
            self.log("ℹ️ Нет времён для заполнения — пропускаю FillTimesStep")
            return

        self.session.click_anchor("cargo_tab")
        self.session.sleep(0.5)

        region = self.session.ui_map.get_region("cargo_search_region")
        left, top, w, h = region

        shot_path = self.session.capture_region("cargo_search_region", "fill_times_cargo.png")

        m_arr = self.session.vision.find(shot_path,
                                         self.session.ui_map.get_template("hdr_arrival_fact"),
                                         region_offset=(left, top), )
        m_dep = self.session.vision.find(shot_path,
                                         self.session.ui_map.get_template("hdr_depart_fact"),
                                         region_offset=(left, top), )
        m_load = self.session.vision.find(shot_path,
                                          self.session.ui_map.get_template("op_load"),
                                          region_offset=(left, top), )
        m_unload = self.session.vision.find(shot_path,
                                            self.session.ui_map.get_template("op_unload"),
                                            region_offset=(left, top), )

        if not m_arr or not m_dep:
            raise RuntimeError("Не найдены заголовки 'Прибытие факт' / 'Убытие факт'")

        if not m_load and not m_unload:
            raise RuntimeError("Не найдены строки 'Погрузка' / 'Разгрузка'")

        # потом можно вернуть в ui_map / json
        # offset_y = self.session.ui_map.get_offset("cargo_fact_row_y", -22)
        # plan_dy = self.session.ui_map.get_offset("cargo_plan_row_dy", 22)
        offset_y = -22
        plan_dy = 22

        x_arr = m_arr.center[0]
        x_dep = m_dep.center[0]

        debug_points = [("hdr_arrival_fact", m_arr.center[0], m_arr.center[1]),
                        ("hdr_depart_fact", m_dep.center[0], m_dep.center[1]), ]

        if m_load:
            y_load = m_load.center[1] + offset_y
            debug_points.append(("op_load", m_load.center[0], m_load.center[1]))
            debug_points.append(("load_arr_cell", x_arr, y_load))
            debug_points.append(("load_dep_cell", x_dep, y_load))
            debug_points.append(("load_deadline", x_dep, y_load + plan_dy))

            ctx.load_arrive_deadline = self._copy_deadline(x_dep,
                                                           y_load,
                                                           plan_dy,
                                                           "load_arrive_deadline")

            if ctx.load_in:
                self._set_cell(x_arr, y_load, ctx.load_in, "Погрузка / Прибытие факт")
            if ctx.load_out:
                self._set_cell(x_dep, y_load, ctx.load_out, "Погрузка / Убытие факт")

        if m_unload:
            y_unload = m_unload.center[1] + offset_y
            debug_points.append(("op_unload", m_unload.center[0], m_unload.center[1]))
            debug_points.append(("unload_arr_cell", x_arr, y_unload))
            debug_points.append(("unload_dep_cell", x_dep, y_unload))
            debug_points.append(("unload_deadline", x_dep, y_unload + plan_dy))

            ctx.unload_arrive_deadline = self._copy_deadline(x_dep,
                                                             y_unload,
                                                             plan_dy, "unload_arrive_deadline")

            if ctx.unload_in:
                self._set_cell(x_arr, y_unload, ctx.unload_in, "Разгрузка / Прибытие факт")
            if ctx.unload_out:
                self._set_cell(x_dep, y_unload, ctx.unload_out, "Разгрузка / Убытие факт")

        self._draw_debug_points(shot_path, debug_points)
        self._store_calc(ctx)

        self.session.click_anchor("start_page_tab")
        self.log("✅ FillTimesStep done: "
                 f"load_arrive_deadline={getattr(ctx, 'load_arrive_deadline', None)!r}, "
                 f"unload_arrive_deadline={getattr(ctx, 'unload_arrive_deadline', None)!r}, "
                 f"calc={ctx.state.get('calc')!r}")
