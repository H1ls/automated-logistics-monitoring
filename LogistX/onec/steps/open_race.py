# LogistX/onec/steps/open_race.py
from __future__ import annotations

import re
import time
from datetime import timedelta

from LogistX.onec.artifacts import OneCArtifacts
from LogistX.onec.race_card_verifier import RaceCardVerifier


class OpenRaceStep:
    stage = "open_race"
    RACE_CODE_RE = re.compile(r"\b[А-ЯA-Z]{2}\d{9}\b", re.IGNORECASE)

    def __init__(self, session, errors, log_func=print, open_timeout: float = 10.0,
                 artifacts=None, race_card_verifier=None):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.open_timeout = open_timeout
        self.artifacts = artifacts or getattr(session, "artifacts", None) or OneCArtifacts(
            session, log_func=log_func
        )
        self.race_card_verifier = race_card_verifier or RaceCardVerifier()

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

    def _is_expected_race_opened_by_ocr(self, ctx) -> bool:
        if not self.session.ui_map.get_optional_template("race_form_header"):
            return False
        if not self.session.find_template_global("race_form_header"):
            return False

        get_optional_region = getattr(self.session.ui_map, "get_optional_region", None)
        capture_region = get_optional_region("race_card_capture_region") if get_optional_region else None
        if not capture_region:
            scale_point = getattr(self.session.ui_map, "scale_point", None)
            width, height = scale_point(600, 560) if scale_point else (600, 560)
            capture_region = (0, 0, width, height)
        shot_path = self.artifacts.capture_rect(self.stage, "race_card_ocr", capture_region)
        try:
            result = self.race_card_verifier.verify(ctx, shot_path)
        except Exception as exc:
            self.log(f"⚠️ OCR-проверка карточки рейса не выполнена: {exc}")
            return False

        ctx.state["race_card_verification"] = {
            "ok": result.ok,
            "race_ok": result.race_ok,
            "unit_ok": result.unit_ok,
            "expected_race": result.expected_race,
            "expected_plate": result.expected_plate,
            "source": "ocr_fallback",
        }
        if result.ok:
            self.log("✅ Карточка нужного рейса подтверждена OCR: рейс, ТС")
            return True

        self.log(
            f"⚠️ OCR не подтвердил карточку ({', '.join(result.failed_fields)}): "
            f"{result.recognized_text!r}"
        )
        return False

    def _is_race_opened(self, ctx) -> bool:
        if self._is_expected_race_opened_by_clipboard(ctx):
            self.log("✅ Карточка нужного рейса подтверждена через Ctrl+C")
            return True
        return self._is_expected_race_opened_by_ocr(ctx)

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
            # Ctrl+C is the fast primary check. Before the slower OCR fallback,
            # handle modal errors which may cover an otherwise opened form.
            if self._is_expected_race_opened_by_clipboard(ctx):
                self.log("✅ Карточка нужного рейса подтверждена через Ctrl+C")
                return True

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

            elif self._is_expected_race_opened_by_ocr(ctx):
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
