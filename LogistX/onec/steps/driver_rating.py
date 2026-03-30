# LogistX/onec/steps/driver_rating.py
from __future__ import annotations

from datetime import datetime


class DriverRatingStep:
    stage = "driver_rating"

    def __init__(self, session, errors, log_func=print, debug_mode: bool = True):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.debug_mode = debug_mode

    def _get_rating_items(self, ctx) -> list[dict]:
        state = getattr(ctx, "state", {}) or {}
        calc = state.get("calc") or {}
        items = calc.get("driver_rating_items") or []
        return [x for x in items if isinstance(x, dict)]

    def _parse_dt(self, s: str) -> datetime | None:
        s = (s or "").strip()
        if not s: return None

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

    def _click_insert_button(self) -> bool:
        region = self.session.ui_map.get_region("rating_region")
        left, top, w, h = region

        shot_path = self.session.capture_region("rating_region", "btn_insert__rating_region.png")

        # if self.debug_mode:
            # self.log(f"🧪 ui_map path: {self.session.ui_map.path}")
            # self.log(f"🧪 templates keys: {list(self.session.ui_map.data.get('templates', {}).keys())}")
            # self.log(f"🧪 regions keys: {list(self.session.ui_map.data.get('regions', {}).keys())}")

        m = self.session.vision.find(shot_path,
                                     self.session.ui_map.get_template("btn_insert"),
                                     region_offset=(left, top), )
        if not m:
            self.log("❌ Не нашёл кнопку '+' (btn_insert)")
            return False

        x, y = m.center
        self.log(f"➕ Нажимаю '+' @ ({x}, {y})")
        self.session.click(x, y)
        self.session.sleep(0.5)
        return True

    def _paste_remote(self, text: str):
        self.session.paste_text(text)
        self.session.sleep(0.1)

    def _add_nothing(self):
        if not self._click_insert_button():
            raise RuntimeError("Не удалось нажать кнопку '+' в оценке водителя")
        self.log("🟩 Оценка водителя: Без отклонений")
        self.session.press("down")
        self.session.sleep(0.15)
        self.session.press("enter")
        self.session.sleep(0.3)

    def _add_driver_deviation(self, kind: str, hours: int):
        if not self._click_insert_button():
            raise RuntimeError("Не удалось нажать кнопку '+' в оценке водителя")

        self.session.sleep(0.3)
        # Поле "Вид отклонения"
        self.log(f"📝 Вид отклонения: {kind}")
        # self.session.press("tab")
        self.session.sleep(0.2)
        self.session.press("f2")
        self.session.sleep(0.2)
        self.session.replace_current_field(kind, submit=False)
        self.session.sleep(0.2)

        # Переходим в поле "Время"
        self.session.press("tab")
        self.session.sleep(0.2)
        # self.log(f"📝 Время: {hours}")
        self.session.press("f2")
        self.session.sleep(0.1)
        self.session.replace_current_field(f'{str(hours)} ч.', submit=True)
        self.session.sleep(0.35)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при добавлении отклонения '{kind}': {err.kind}")

    def run(self, ctx):
        items = self._get_rating_items(ctx)

        self.log("⭐ Перехожу на вкладку оценки водителя")

        anchor = self.session.ui_map.get_optional_anchor("driver_rating_tab")
        if anchor:
            self.session.click(*anchor)
        else:
            tpl = self.session.ui_map.get_optional_template("driver_rating_tab")
            if tpl:
                m = self.session.find_template_global("driver_rating_tab")
                if not m:
                    raise RuntimeError("Не удалось найти вкладку оценки водителя")
                self.session.click(*m.center)
            else:
                raise RuntimeError("Не задан ни anchor, ни template для driver_rating_tab")

        self.session.sleep(0.5)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при переходе на оценку водителя: {err.kind}")

        if not items:
            self._add_nothing()
            return

        for item in items:
            kind = str(item.get("kind") or "").strip()
            hours = int(item.get("hours") or 0)
            if not kind or hours <= 0:
                continue

            self.log(f"🟧 {kind}: {hours} ч.")
            self._add_driver_deviation(kind, hours)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка в блоке оценки водителя: {err.kind}")