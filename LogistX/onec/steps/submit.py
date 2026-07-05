from __future__ import annotations

from datetime import datetime
import time

from LogistX.onec.checkbox import CheckboxController
from LogistX.onec.steps.base_code import fmt_date, fmt_time, replace_focused_field, require_dt
from LogistX.onec.steps.ui_point_resolver import UiPointResolver
from Navigation_Bot.core.logging import normalize_log_func


class SubmitStep:
    stage = "submit"

    def __init__(self, session, error_handler, log_func=print, point_resolver=None,
                 checkbox_controller=None, submit_timeout: float = 6.0):
        self.session = session
        self.errors = error_handler
        self.log = normalize_log_func(log_func)
        self.points = point_resolver or UiPointResolver(session)
        self.checkboxes = checkbox_controller or CheckboxController(session, log_func=self.log)
        self.submit_timeout = max(0.1, float(submit_timeout))

    def _check_error(self, prefix: str):
        err = self.errors.detect()
        if err:
            self.errors.close_error_dialog()
            raise RuntimeError(f"{prefix}: {err.kind}")

    def _resolve_finish_dt(self, ctx) -> datetime:
        if not ctx.unload_out:
            raise RuntimeError("Не заполнено ctx.unload_out для закрытия рейса")
        return require_dt(ctx.unload_out)

    def _get_finish_coords(self, ctx=None):
        departure_label = self.points.resolve("departure_label", ctx=ctx)
        label_x, label_y = departure_label.x, departure_label.y

        row_dx, row_dy = self.session.ui_map.get_offset("finish_row_from_departure_label")
        date_dx, _ = self.session.ui_map.get_offset("departure_date_field_from_departure_label")
        time_dx, _ = self.session.ui_map.get_offset("departure_time_field_from_departure_label")

        finish_checkbox = (label_x + row_dx, label_y + row_dy)
        finish_date = (label_x + date_dx, label_y + row_dy)
        finish_time = (label_x + time_dx, label_y + row_dy)

        return finish_checkbox, finish_date, finish_time

    def _click_xy(self, x: int, y: int, pause: float = 0.25):
        self.session.click(x, y)
        self.session.sleep(pause)

    def _fill_xy_field(self, x: int, y: int, value: str, label: str):
        self.log(f"📝 {label}: {value}")
        self.session.click(x, y)
        replace_focused_field(self.session, value, after_sleep=0.25)

    def _is_race_form_open(self) -> bool:
        if not self.session.ui_map.get_optional_template("race_form_header"):
            raise RuntimeError("В ui_map не задан шаблон race_form_header для проверки закрытия рейса")
        return bool(self.session.find_template_global("race_form_header"))

    def _wait_submission_confirmed(self) -> None:
        deadline = time.monotonic() + self.submit_timeout
        absent_checks = 0
        while time.monotonic() < deadline:
            self._check_error("Ошибка при закрытии рейса")
            if self._is_race_form_open():
                absent_checks = 0
            else:
                absent_checks += 1
                if absent_checks >= 2:
                    return
            self.session.sleep(0.35)
        raise RuntimeError("1С не подтвердила закрытие рейса: карточка рейса осталась открыта")

    def run(self, ctx):
        self.log("\n=== STEP: submit ===")

        finish_dt = self._resolve_finish_dt(ctx)
        finish_date_str = fmt_date(finish_dt)
        finish_time_str = fmt_time(finish_dt)

        self.log("📑 Перехожу на вкладку параметров рейса")
        self.points.click("race_params_tab", ctx=ctx)
        self.session.sleep(0.35)
        self._check_error("Ошибка после перехода на вкладку параметров рейса")

        finish_checkbox_xy, finish_date_xy, finish_time_xy = self._get_finish_coords(ctx=ctx)

        self.log("☑️ Активирую строку 'Выполнен'")
        self.checkboxes.ensure_checked(
            finish_checkbox_xy, stage=self.stage, name="finished"
        )
        self._check_error("Ошибка после нажатия 'Выполнен'")

        self._fill_xy_field(*finish_date_xy, finish_date_str, "Дата выполнения")
        self._check_error("Ошибка после ввода даты выполнения")

        self._fill_xy_field(*finish_time_xy, finish_time_str, "Время выполнения")
        self._check_error("Ошибка после ввода времени выполнения")

        self.session.submit_ctrl_enter()
        self._wait_submission_confirmed()

        ctx.state["submitted"] = True
        ctx.state["finish_dt"] = finish_dt
        ctx.state["close_status"] = "closed"
        self.log(f"✅ Рейс закрыт: {finish_dt:%d.%m.%Y %H:%M}")
