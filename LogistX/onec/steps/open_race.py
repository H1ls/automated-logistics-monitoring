# LogistX/onec/steps/open_race.py
from __future__ import annotations

import re
import time
from datetime import timedelta


class OpenRaceStep:
    stage = "open_race"
    RACE_CODE_RE = re.compile(r"\b[А-ЯA-Z]{2}\d{9}\b", re.IGNORECASE)

    def __init__(self, session, errors, log_func=print, open_timeout: float = 10.0):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.open_timeout = open_timeout

    def _extract_expected_race_code(self, ctx) -> str | None:
        text = (ctx.race_name or "").strip()
        m = self.RACE_CODE_RE.search(text)
        return m.group(0).upper() if m else None

    def _extract_race_code_from_text(self, text: str) -> str | None:
        text = (text or "").strip()
        m = self.RACE_CODE_RE.search(text)
        return m.group(0).upper() if m else None

    def _is_expected_race_opened_by_clipboard(self, ctx) -> bool:
        expected_code = self._extract_expected_race_code(ctx)
        if not expected_code:
            self.log("⚠️ Не смог извлечь ожидаемый номер рейса из ctx.race_name")
            return False

        self.session.clear_clipboard()
        self.session.hotkey("ctrl", "c")
        self.session.sleep(0.15)

        copied = self.session.copy_clipboard()
        copied_code = self._extract_race_code_from_text(copied)

        self.log(f"📋 Ctrl+C buffer: {copied!r}")
        self.log(f"🔎 expected_code={expected_code}, copied_code={copied_code}")

        if copied_code and copied_code == expected_code:
            ctx.state["opened_race_code"] = copied_code
            return True

        return False

    def _is_race_opened(self, ctx) -> bool:
        # 1. быстрый и главный способ — по Ctrl+C
        if self._is_expected_race_opened_by_clipboard(ctx):
            self.log("✅ Карточка нужного рейса подтверждена через Ctrl+C")
            return True

        # 2. fallback по шаблону, если он есть
        template = self.session.ui_map.get_optional_template("race_form_header")
        if template:
            m = self.session.find_template_global("race_form_header")
            if m:
                self.log("ℹ️ Найден race_form_header, но номер рейса через Ctrl+C не подтвердился")
                return True

        return False

    def _open_by_keyboard(self):
        self.log("⌨️ Открываю рейс: Enter -> Down -> Enter")
        self.session.press("enter")
        self.session.sleep(0.35)
        self.session.press("down")
        self.session.sleep(0.35)
        self.session.press("enter")
        self.session.sleep(0.55)

    def _process_detected_error(self, ctx, err):
        self.log(f"⚠️ Обнаружено состояние ошибки: {err.kind}; text={err.text}")

        ctx.state["open_race_error_kind"] = err.kind
        ctx.state["open_race_error_text"] = err.text

        if err.kind == "date_conflict":
            if err.finish_dt:
                ctx.state["open_race_finish_dt"] = err.finish_dt
                ctx.state["suggested_departure_dt"] = err.finish_dt + timedelta(minutes=1)
                self.log(f"🧠 finish_dt={ctx.state['open_race_finish_dt']}, "
                         f"suggested_departure_dt={ctx.state['suggested_departure_dt']}")

            self.errors.close_error_dialog()
            return "continue_wait"

        if err.kind == "locked_by_user":
            self.errors.close_error_dialog()
            raise RuntimeError("Рейс открыт другим пользователем")

        if err.kind == "unknown_dialog":
            self.errors.close_error_dialog()
            self.session.sleep(0.8)

            # после закрытия диалога ещё раз проверяем, не открылась ли карточка
            if self._is_race_opened(ctx):
                self.log("✅ После закрытия диалога карточка всё-таки открылась")
                return "opened_after_dialog"

            return "continue_wait"

        self.errors.close_error_dialog()
        raise RuntimeError(f"Ошибка при открытии рейса: {err.kind}")

    def _wait_open_result(self, ctx) -> bool:
        start = time.time()
        saw_date_conflict = False

        while time.time() - start < self.open_timeout:
            # Сначала пробуем понять, что рейс уже открыт
            if self._is_race_opened(ctx):
                return True

            # Потом проверяем ошибки
            err = self.errors.detect()
            if err:
                action = self._process_detected_error(ctx, err)
                if err.kind == "date_conflict":
                    saw_date_conflict = True

                if action == "continue_wait":
                    self.session.sleep(0.6)
                    continue

                if action == "opened_after_dialog":
                    return True

            self.log("⏳ Жду открытия рейса...")
            self.session.sleep(0.6)

        if saw_date_conflict:
            raise RuntimeError("После ошибки пересечения карточка рейса не открылась")

        raise RuntimeError("Не удалось открыть рейс: таймаут ожидания")

    def run(self, ctx):
        self.log("📂 Открываю найденный рейс")
        self._open_by_keyboard()
        self._wait_open_result(ctx)
