# LogistX/onec/steps/fill_times.py
from __future__ import annotations

from LogistX.onec.artifacts import OneCArtifacts
from LogistX.onec.steps.base_code import ensure_state_dict, fmt_dt_1c
from LogistX.onec.steps.ui_point_resolver import UiPointResolver
from LogistX.onec.trip_time_calculator import TripTimeCalculator, TripTimeInput
from Navigation_Bot.core.logging import normalize_log_func


class FillTimesStep:
    stage = "fill_times"

    def __init__(self, session, errors, log_func=print, point_resolver=None, artifacts=None,
                 calculator=None):
        self.session = session
        self.errors = errors
        self.log = normalize_log_func(log_func)
        self.points = point_resolver or UiPointResolver(session)
        self.artifacts = artifacts or getattr(session, "artifacts", None) or OneCArtifacts(session, log_func=self.log)
        self.calculator = calculator or TripTimeCalculator()

    def _copy_deadline(self, x_dep: int, y_row: int, plan_dy: int, label: str) -> str:
        x = x_dep
        y = y_row + plan_dy
        text = self.session.copy_cell_text(x, y)
        self.log(f"📋 {label}: copy deadline from ({x}, {y}) -> {text!r}")
        return text

    def _set_cell(self, x: int, y: int, value: str, label: str):
        value = fmt_dt_1c(value)
        self.log(f"📝 {label}: {value} -> ({x}, {y})")
        self.session.replace_cell(x, y, value, submit=True)
        self.session.sleep(0.25)

        err = self.errors.detect()
        if err:
            self.errors.close_error_dialog()
            raise RuntimeError(f"Ошибка при заполнении {label}: {err.kind}")

    def _store_calc(self, ctx):
        calc = ensure_state_dict(ctx, "calc")
        result = self.calculator.calculate(TripTimeInput(
            load_in=ctx.load_in,
            load_out=ctx.load_out,
            unload_in=ctx.unload_in,
            unload_out=ctx.unload_out,
            load_arrive_deadline=getattr(ctx, "load_arrive_deadline", None),
            unload_arrive_deadline=getattr(ctx, "unload_arrive_deadline", None),
        ))
        calc.update(result)

        if result["driver_rating_items"]:
            self.log(f"🧾 driver_rating_items={result['driver_rating_items']}")
        else:
            self.log("🧾 driver_rating_items=[] -> Без отклонений")

    def run(self, ctx):
        has_any = any([ctx.load_in, ctx.load_out, ctx.unload_in, ctx.unload_out])
        if not has_any:
            self.log("ℹ️ Нет времён для заполнения — пропускаю FillTimesStep")
            return

        self.points.click("cargo_tab", ctx=ctx)
        self.session.sleep(0.5)

        region = self.session.ui_map.get_region("cargo_search_region")
        left, top, w, h = region

        shot_path = self.artifacts.capture_region(self.stage, "cargo_search", "cargo_search_region")
        debug_screen = self.artifacts.capture_full(self.stage, "regions_source", debug_only=True)
        if debug_screen:
            self.artifacts.annotate_regions(debug_screen, self.stage, "regions",["cargo_search_region",
                                                                                                   "error_header_region",
                                                                                                   "error_search_region",
                                                                                                   "error_buttons_region",
                                                                                                   "error_text_region"])

        m_arr = self.session.vision.find(shot_path,
                                         self.session.ui_map.get_template("hdr_arrival_fact"),region_offset=(left, top))
        m_dep = self.session.vision.find(shot_path,
                                         self.session.ui_map.get_template("hdr_depart_fact"),region_offset=(left, top))
        m_load = self.session.vision.find(shot_path,
                                          self.session.ui_map.get_template("op_load"),region_offset=(left, top))
        m_unload = self.session.vision.find(shot_path,
                                            self.session.ui_map.get_template("op_unload"),region_offset=(left, top))

        if not m_arr or not m_dep:
            raise RuntimeError("Не найдены заголовки 'Прибытие факт' / 'Убытие факт'")

        if not m_load and not m_unload:
            raise RuntimeError("Не найдены строки 'Погрузка' / 'Разгрузка'")

        _, offset_y = self.session.ui_map.get_offset("cargo_fact_row_y")
        _, plan_dy = self.session.ui_map.get_offset("cargo_plan_row_dy")

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

            ctx.load_arrive_deadline = self._copy_deadline(x_dep,y_load,plan_dy,"load_arrive_deadline")

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

            ctx.unload_arrive_deadline = self._copy_deadline(x_dep,y_unload,plan_dy, "unload_arrive_deadline")

            if ctx.unload_in:
                self._set_cell(x_arr, y_unload, ctx.unload_in, "Разгрузка / Прибытие факт")
            if ctx.unload_out:
                self._set_cell(x_dep, y_unload, ctx.unload_out, "Разгрузка / Убытие факт")

        self.artifacts.annotate_points(shot_path,self.stage,"cargo_points",debug_points,origin=(left, top),)

        self._store_calc(ctx)

        self.points.click("start_page_tab", ctx=ctx)
        # self.log("✅ FillTimesStep done: "
        #          f"load_arrive_deadline={getattr(ctx, 'load_arrive_deadline', None)!r}, "
        #          f"unload_arrive_deadline={getattr(ctx, 'unload_arrive_deadline', None)!r}, "
        #          f"calc={ctx.state.get('calc')!r}")
