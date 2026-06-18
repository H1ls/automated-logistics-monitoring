from __future__ import annotations

from LogistX.onec.steps.base_code import ensure_state, positive_minutes_between


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

    def _get_ctx_point(self, ctx, name: str):
        if not ctx:
            return None
        ui_points = (getattr(ctx, "state", {}) or {}).get("ui_points") or {}
        point = ui_points.get(name)
        if not point:
            return None
        return int(point["x"]), int(point["y"])

    def _click_point(self, name: str, ctx=None):
        point = self._get_ctx_point(ctx, name)
        if point:
            x, y = point
            # self.log(f"→ click ctx ui_point: {name} @ ({x}, {y})")
            self.session.click(x, y)
            return

        anchor = self.session.ui_map.get_optional_anchor(name)
        if anchor:
            x, y = anchor
            # self.log(f"→ click ui_map anchor: {name} @ ({x}, {y})")
            self.session.click(x, y)
            return

        tpl = self.session.ui_map.get_optional_template(name)
        if tpl:
            m = self.session.find_template_global(name)
            if not m:
                raise RuntimeError(f"Не удалось найти '{name}'")
            x, y = m.center
            # self.log(f"→ click template match: {name} @ ({x}, {y})")
            self.session.click(x, y)
            return

        raise RuntimeError(f"Не задан ни ctx/ui_map/template для {name}")

    def _open_driver_rating(self, ctx=None):
        self.log("⭐ Перехожу на вкладку оценки водителя")
        self._click_point("driver_rating_tab", ctx=ctx)
        self.session.sleep(0.4)

    def _apply_wait_load_if_needed(self, ctx, threshold_hours: int = 10):
        wait_minutes = positive_minutes_between(getattr(ctx, "departure_dt", None),
                                                getattr(ctx, "load_in", None))
        ensure_state(ctx)["wait_load_minutes"] = wait_minutes

        if wait_minutes is None or wait_minutes <= threshold_hours * 60:
            return

        self.log(f"⏳ Ожидание погрузки {wait_minutes} мин > {threshold_hours}ч - ставлю галку")
        self._click_point("wait_load", ctx=ctx)
        self.session.sleep(0.25)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при установке галки 'Ожидание погрузки': {err.kind}")

    def _click_insert_button(self) -> bool:
        region = self.session.ui_map.get_optional_region("rating_region")

        if region:
            left, top, w, h = region
            shot_path = self.session.capture_region("rating_region", "btn_insert__rating_region.png")
            region_offset = (left, top)
            # self.log(f"🧭 Ищу '+' в rating_region={region}")
        else:
            shot_path = self.session.capture_current_race_form("btn_insert__full.png")
            region_offset = (0, 0)
            self.log("⚠️ rating_region не задан — ищу '+' по всему экрану")

        m = self.session.vision.find(shot_path,
                                     self.session.ui_map.get_template("btn_insert"),
                                     region_offset=region_offset,)
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
        self.log(f"📝 Вид отклонения: {kind}")
        self.session.sleep(0.2)
        self.session.press("f2")
        self.session.sleep(0.2)
        self.session.replace_current_field(kind, submit=False)
        self.session.sleep(0.2)

        self.session.press("tab")
        self.session.sleep(0.2)
        self.log(f"📝 Время: {hours}")
        self.session.press("f2")
        self.session.sleep(0.1)
        self.session.replace_current_field(f"{hours} ч.", submit=True)
        self.session.sleep(0.35)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при добавлении отклонения '{kind}': {err.kind}")

    def run(self, ctx):
        items = self._get_rating_items(ctx)

        self.log("Возврат на Основную вкладку")
        self._click_point("start_page_tab", ctx=ctx)
        self.session.sleep(0.5)
        self._apply_wait_load_if_needed(ctx)
        self._open_driver_rating(ctx=ctx)
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
