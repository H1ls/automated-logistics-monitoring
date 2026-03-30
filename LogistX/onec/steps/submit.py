# LogistX/onec/steps/submit.py
from __future__ import annotations

from datetime import datetime


class SubmitStep:
    stage = "submit"

    def __init__(self, session, error_handler, log_func=print):
        self.session = session
        self.errors = error_handler
        self.log = log_func

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        value = (value or "").strip()
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        raise ValueError(f"Не удалось распарсить datetime: {value!r}")

    @staticmethod
    def _fmt_date(dt: datetime) -> str:
        return dt.strftime("%d.%m.%Y")

    @staticmethod
    def _fmt_time(dt: datetime) -> str:
        return dt.strftime("%H:%M")

    def _check_error(self, prefix: str):
        err = self.errors.detect()
        if err:
            self.errors.close_error_dialog()
            raise RuntimeError(f"{prefix}: {err.kind}")

    def _resolve_finish_dt(self, ctx) -> datetime:
        if not ctx.unload_out:
            raise RuntimeError("Не заполнено ctx.unload_out для закрытия рейса")
        return self._parse_dt(ctx.unload_out)

    def _get_finish_coords(self):
        """
        Строим координаты от departure_label:
        - finish_checkbox = departure_label + finish_row_from_departure_label
        - finish_date     = finish_row + departure_date_field_from_departure_label
        - finish_time     = finish_row + departure_time_field_from_departure_label
        """
        label_x, label_y = self.session.ui_map.get_anchor("departure_label")

        row_dx, row_dy = self.session.ui_map.get_offset("finish_row_from_departure_label")
        date_dx, _ = self.session.ui_map.get_offset("departure_date_field_from_departure_label")
        time_dx, _ = self.session.ui_map.get_offset("departure_time_field_from_departure_label")

        finish_checkbox = (label_x + row_dx, label_y + row_dy)
        finish_date = (label_x + date_dx, label_y + row_dy)
        finish_time = (label_x + time_dx, label_y + row_dy)

        return finish_checkbox, finish_date, finish_time

    def _click_xy(self, x: int, y: int, label: str | None = None, pause: float = 0.25):
        if label:
            pass
            # self.log(f"→ click: {label} @ ({x}, {y})")
        self.session.click(x, y)
        self.session.sleep(pause)

    def _fill_xy_field(self, x: int, y: int, value: str, label: str):
        self.log(f"📝 {label}: {value}")
        self.session.click(x, y)
        self.session.sleep(0.08)
        self.session.press("f2")
        self.session.sleep(0.08)
        self.session.replace_current_field(value, submit=False)
        self.session.sleep(0.25)

    def run(self, ctx):
        self.log("\n=== STEP: submit ===")

        finish_dt = self._resolve_finish_dt(ctx)
        finish_date_str = self._fmt_date(finish_dt)
        finish_time_str = self._fmt_time(finish_dt)

        # 1. Вкладка параметров рейса
        self.log("📑 Перехожу на вкладку параметров рейса")
        self.session.click_anchor("race_params_tab")
        self.session.sleep(0.35)
        self._check_error("Ошибка после перехода на вкладку параметров рейса")

        # 2. Координаты строки 'Выполнен'
        finish_checkbox_xy, finish_date_xy, finish_time_xy = self._get_finish_coords()

        # 3. Нажать 'Выполнен'
        self.log("☑️ Активирую строку 'Выполнен'")
        self._click_xy(*finish_checkbox_xy, label="finish_checkbox")
        self._check_error("Ошибка после нажатия 'Выполнен'")

        # 4. Ввести дату выполнения
        self._fill_xy_field(*finish_date_xy, finish_date_str, "Дата выполнения")
        self._check_error("Ошибка после ввода даты выполнения")

        # 5. Ввести время выполнения
        self._fill_xy_field(*finish_time_xy, finish_time_str, "Время выполнения")
        self._check_error("Ошибка после ввода времени выполнения")

        # 6. Сохранить / закрыть рейс
        # self.log("💾 Ctrl+Enter")
        self.session.submit_ctrl_enter()
        self.session.sleep(0.4)
        self._check_error("Ошибка при закрытии рейса")

        ctx.state["submitted"] = True
        ctx.state["finish_dt"] = finish_dt
        self.log(f"✅ Рейс закрыт: {finish_dt:%d.%m.%Y %H:%M}")