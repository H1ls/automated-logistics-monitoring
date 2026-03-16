# LogistX/onec/steps/driver_rating.py
from __future__ import annotations

from datetime import datetime


class DriverRatingStep:
    stage = "driver_rating"

    def __init__(self, session, errors, log_func=print):
        self.session = session
        self.errors = errors
        self.log = log_func

    def _parse_dt(self, s: str) -> datetime | None:
        s = (s or "").strip()
        if not s:
            return None

        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
            try:
                return datetime.strptime(s[:19], fmt)
            except Exception:
                pass
        return None

    def _calc_minutes_diff(self, a: str, b: str) -> int | None:
        da = self._parse_dt(a)
        db = self._parse_dt(b)
        if not da or not db:
            return None
        return int((da - db).total_seconds() // 60)

    def _calc_stay_minutes(self, start: str, end: str) -> int | None:
        ds = self._parse_dt(start)
        de = self._parse_dt(end)
        if not ds or not de:
            return None
        mins = int((de - ds).total_seconds() // 60)
        return mins if mins >= 0 else None

    def _round_stay_hours(self, total_minutes: int | None) -> int:
        if total_minutes is None or total_minutes <= 0:
            return 0
        hours = total_minutes // 60
        rem = total_minutes % 60
        if rem > 45:
            hours += 1
        return int(hours)

    def _ceil_late_hours(self, total_minutes: int | None) -> int:
        if total_minutes is None or total_minutes <= 0:
            return 0
        hours = total_minutes // 60
        rem = total_minutes % 60
        if rem > 0:
            hours += 1
        return int(hours)

    def _over_6h_hours(self, stay_hours: int) -> int:
        return max(0, int(stay_hours) - 6)

    def _open_driver_rating(self):
        self.log("⭐ Перехожу на вкладку оценки водителя")

        anchor = self.session.ui_map.get_optional_anchor("driver_rating_tab")
        if anchor:
            self.session.click(*anchor)
            self.session.sleep(0.4)
            return

        tpl = self.session.ui_map.get_optional_template("driver_rating_tab")
        if tpl:
            m = self.session.find_template_global("driver_rating_tab")
            if not m:
                raise RuntimeError("Не удалось найти вкладку оценки водителя")
            self.session.click(*m.center)
            self.session.sleep(0.4)
            return

        raise RuntimeError("Не задан ни anchor, ни template для driver_rating_tab")

    def _click_insert_button(self):
        m = self.session.find_template_in_region("btn_insert", "rating_region")
        if not m:
            raise RuntimeError("Не нашёл кнопку INS")
        self.session.click(*m.center)
        self.session.sleep(0.4)

    def _paste_remote(self, text: str):
        self.session.paste_text(text)
        self.session.sleep(0.1)

    def _add_nothing(self, text: str):
        self._click_insert_button()
        self._paste_remote(text)

    def _add_driver_deviation(self, text: str, hours: int):
        self._click_insert_button()

        self._paste_remote(text)
        self.session.sleep(0.2)

        self.session.press("f2")
        self.session.sleep(0.15)
        self.session.press("enter")
        self.session.sleep(0.2)

        self.session.press("right")
        self.session.sleep(0.15)
        self.session.press("enter")
        self.session.sleep(0.2)

        self._paste_remote(f"{hours} ч.")
        self.session.sleep(0.2)

        self.session.press("enter")
        self.session.sleep(0.2)

    def run(self, ctx):
        calc = ctx.state.get("calc") or {}
        if not calc:
            self.log("ℹ️ Нет calc в ctx.state — DriverRatingStep пропущен")
            return

        load_late_min = calc.get("load_lateness_minutes")
        unload_late_min = calc.get("unload_lateness_minutes")

        load_stay_h = int(calc.get("load_stay_hours") or 0)
        unload_stay_h = int(calc.get("unload_stay_hours") or 0)

        load_late_h = self._ceil_late_hours(load_late_min)
        unload_late_h = self._ceil_late_hours(unload_late_min)

        load_over6 = self._over_6h_hours(load_stay_h)
        unload_over6 = self._over_6h_hours(unload_stay_h)

        write_load_over6 = load_over6 > 1
        write_unload_over6 = unload_over6 > 1

        self.log(f"📊 DriverRating calc | "
                 f"load_late_min={load_late_min}, unload_late_min={unload_late_min}, "
                 f"load_stay_h={load_stay_h}, unload_stay_h={unload_stay_h}, "
                 f"load_late_h={load_late_h}, unload_late_h={unload_late_h}, "
                 f"load_over6={load_over6}, unload_over6={unload_over6}")

        self._open_driver_rating()

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при переходе на оценку водителя: {err.kind}")

        has_any = ((load_late_h > 0) or
                   (unload_late_h > 0) or
                   write_load_over6 or
                   write_unload_over6)

        if not has_any:
            self.log("🟩 Оценка водителя: Без отклонений")
            self._add_nothing("Без отклонений")
            return

        if load_late_h > 0:
            self.log(f"🟨 Опоздание на погрузку: {load_late_h} ч.")
            self._add_driver_deviation("Опоздание на погрузку", load_late_h)

        if unload_late_h > 0:
            self.log(f"🟨 Опоздание на разгрузку: {unload_late_h} ч.")
            self._add_driver_deviation("Опоздание на разгрузку", unload_late_h)

        if write_load_over6:
            self.log(f"🟧 Простой на погрузке: {load_over6} ч.")
            self._add_driver_deviation("Простой на погрузке", load_over6)

        if write_unload_over6:
            self.log(f"🟧 Простой на разгрузке: {unload_over6} ч.")
            self._add_driver_deviation("Простой на разгрузке", unload_over6)
