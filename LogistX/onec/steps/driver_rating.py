from __future__ import annotations

from collections import Counter

from LogistX.onec.artifacts import OneCArtifacts
from LogistX.onec.checkbox import CheckboxController
from LogistX.onec.driver_rating_table import DriverRatingTableReader
from LogistX.onec.steps.base_code import ensure_state, positive_minutes_between
from LogistX.onec.steps.ui_point_resolver import UiPointResolver


class DriverRatingStep:
    stage = "driver_rating"

    def __init__(self, session, errors, log_func=print, point_resolver=None, artifacts=None,
                 table_reader=None, verify_attempts: int = 3, checkbox_controller=None):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.points = point_resolver or UiPointResolver(session)
        self.artifacts = artifacts or getattr(session, "artifacts", None) or OneCArtifacts(session, log_func=log_func)
        self.table_reader = table_reader or DriverRatingTableReader()
        self.verify_attempts = max(1, int(verify_attempts))
        self.checkboxes = checkbox_controller or CheckboxController(session, artifacts=self.artifacts)

    def _get_rating_items(self, ctx) -> list[dict]:
        state = getattr(ctx, "state", {}) or {}
        calc = state.get("calc") or {}
        items = calc.get("driver_rating_items") or []
        return [x for x in items if isinstance(x, dict)]

    def _click_point(self, name: str, ctx=None):
        self.points.click(name, ctx=ctx)

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
        anchor = self.points.resolve("wait_load", ctx=ctx)
        dx, dy = self.session.ui_map.get_offset("wait_load_checkbox_from_anchor")
        self.checkboxes.ensure_checked(
            (anchor.x + dx, anchor.y + dy), stage=self.stage, name="wait_load"
        )

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при установке галки 'Ожидание погрузки': {err.kind}")

    def _find_insert_button(self):
        region = self.session.ui_map.get_optional_region("rating_region")

        if region:
            left, top, w, h = region
            shot_path = self.artifacts.capture_region(self.stage, "insert_button", "rating_region")
            region_offset = (left, top)
            # self.log(f"🧭 Ищу '+' в rating_region={region}")
        else:
            shot_path = self.artifacts.capture_full(self.stage, "insert_button_full")
            region_offset = (0, 0)
            self.log("⚠️ rating_region не задан — ищу '+' по всему экрану")

        return self.session.vision.find(shot_path,
                                        self.session.ui_map.get_template("btn_insert"),
                                        region_offset=region_offset,)

    def _click_insert_button(self) -> bool:
        m = self._find_insert_button()
        if not m:
            self.log("❌ Не нашёл кнопку '+' (btn_insert)")
            return False

        x, y = m.center
        self.log(f"➕ Нажимаю '+' @ ({x}, {y})")
        self.session.click(x, y)
        self.session.sleep(0.5)
        return True

    @staticmethod
    def _expected_rows(items: list[dict]) -> list[tuple[str, int]]:
        rows = []
        for item in items:
            kind = str(item.get("kind") or "").strip()
            hours = int(item.get("hours") or 0)
            if kind and hours > 0:
                rows.append((kind, hours))
        return rows or [("Без отклонений", 0)]

    def _capture_rating_table(self):
        if not self.session.ui_map.get_optional_region("rating_table_region"):
            raise RuntimeError("В ui_map не задан rating_table_region")
        return self.artifacts.capture_region(self.stage, "table_verification", "rating_table_region")

    def _delete_rating_row(self, row) -> None:
        left, top, width, _ = self.session.ui_map.get_region("rating_table_region")
        self.session.click(left + min(300, width - 30), top + row.y)
        self.session.sleep(0.15)

        insert_button = self._find_insert_button()
        if not insert_button:
            raise RuntimeError("Не найдена кнопка '+' для определения кнопки удаления")
        dx, dy = self.session.ui_map.get_offset("rating_delete_from_insert")
        self.log(f"🗑 Удаляю неверную строку: {row.text}")
        self.session.click(insert_button.center[0] + dx, insert_button.center[1] + dy)
        self.session.sleep(0.35)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при удалении строки оценки: {err.kind}")

    def _add_expected_row(self, key: tuple[str, int]) -> None:
        kind, hours = key
        if kind == "Без отклонений":
            self._add_nothing()
        else:
            self._add_driver_deviation(kind, hours)

    def _verify_and_repair(self, ctx, items: list[dict]) -> None:
        expected = Counter(self._expected_rows(items))

        for attempt in range(1, self.verify_attempts + 1):
            snapshot = self.table_reader.read(self._capture_rating_table())
            actual = Counter(row.key for row in snapshot.rows)

            ensure_state(ctx)["driver_rating_verification"] = {
                "attempt": attempt,
                "ok": actual == expected,
                "expected": list(expected.elements()),
                "actual": list(actual.elements()),
                "recognized_text": snapshot.recognized_text,
            }

            if actual == expected:
                self.log(f"✅ Оценка водителя проверена, попытка {attempt}")
                return

            if not snapshot.rows:
                self.log(f"⚠️ OCR не распознал строки оценки: {snapshot.recognized_text!r}")
                if attempt < self.verify_attempts:
                    self.session.sleep(0.4)
                    continue
                raise RuntimeError("Не удалось распознать таблицу оценки водителя")

            if attempt >= self.verify_attempts:
                raise RuntimeError(
                    f"Оценка водителя не совпала после {self.verify_attempts} попыток: "
                    f"expected={list(expected.elements())}, actual={list(actual.elements())}"
                )

            remaining = expected.copy()
            extra_rows = []
            for row in snapshot.rows:
                if remaining[row.key] > 0:
                    remaining[row.key] -= 1
                else:
                    extra_rows.append(row)

            for row in sorted(extra_rows, key=lambda value: value.y, reverse=True):
                self._delete_rating_row(row)

            for key, count in remaining.items():
                for _ in range(count):
                    self.log(f"🔁 Повторно добавляю: {key[0]} = {key[1]} ч.")
                    self._add_expected_row(key)

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
            self._verify_and_repair(ctx, items)
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

        self._verify_and_repair(ctx, items)
