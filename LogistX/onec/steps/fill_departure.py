from __future__ import annotations

import re
from datetime import date, datetime, timedelta


class FillDepartureStep:
    stage = "fill_departure"

    def __init__(self, session, errors, log_func=print, max_rounds: int = 5):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.max_rounds = max_rounds

    def _parse_dt(self, value: str | datetime | date | None) -> datetime:
        """Строка в формате дд.мм.гггг чч:мм[(:сс)] или уже datetime/date."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, datetime.min.time())
        value = (value or "").strip()
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        raise ValueError(f"Не удалось распарсить datetime: {value!r}")

    @staticmethod
    def _parse_race_dt(race_name: str) -> datetime | None:
        """Поддерживает: '... от 07.03.2026 19:38:35', '... от 16.03.2026 9:43:59'"""
        text = (race_name or "").strip()
        m = re.search(r"от\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{1,2}:\d{2})(?::\d{2})?", text)
        if not m:
            return None

        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M")
        except ValueError:
            return None

    @staticmethod
    def _fmt_date(dt: datetime) -> str:
        return dt.strftime("%d.%m.%Y")

    @staticmethod
    def _fmt_time(dt: datetime) -> str:
        return dt.strftime("%H:%M")

    @staticmethod
    def _ensure_state(ctx) -> dict:
        if not hasattr(ctx, "state") or ctx.state is None:
            ctx.state = {}
        return ctx.state

    def _saved_progress(self, ctx) -> dict:
        meta = getattr(ctx, "meta", {}) or {}
        progress = meta.get("saved_onec_progress") or {}
        return progress if isinstance(progress, dict) else {}

    def _saved_departure_dt(self, ctx) -> str:
        meta = getattr(ctx, "meta", {}) or {}
        return str(meta.get("saved_departure_dt_1c", "") or "").strip()

    def _should_skip_by_saved_state(self, ctx) -> tuple[bool, str]:
        """
        Пропускаем повторный ввод, если уже ранее сохранили:
        - departure_filled = True
        - departure_dt_1c не пустой
        """
        progress = self._saved_progress(ctx)
        saved_departure = self._saved_departure_dt(ctx)

        if progress.get("departure_filled") and saved_departure:
            return True, saved_departure

        return False, ""

    def _restore_saved_departure(self, ctx, saved_value: str):
        """
        Восстанавливаем время в ctx без повторного ввода в 1С.
        """
        state = self._ensure_state(ctx)

        dt = self._parse_dt(saved_value).replace(second=0, microsecond=0)

        ctx.departure_dt = dt.strftime("%d.%m.%Y %H:%M")
        state["final_departure_dt"] = dt
        state["suggested_departure_dt"] = dt

        progress = state.get("onec_progress")
        if not isinstance(progress, dict):
            progress = {}
            state["onec_progress"] = progress
        progress["departure_filled"] = True

        self.log(f"ℹ️ Пропускаю FillDepartureStep — уже было выставлено ранее: {ctx.departure_dt}")

    def _resolve_initial_dt(self, ctx) -> datetime:
        suggested = ctx.state.get("suggested_departure_dt")
        if isinstance(suggested, datetime):
            self.log(f"🧠 Базовое время из suggested_departure_dt: {suggested:%d.%m.%Y %H:%M}")
            return suggested.replace(second=0, microsecond=0)

        if ctx.departure_dt:
            dt = self._parse_dt(ctx.departure_dt).replace(second=0, microsecond=0)
            self.log(f"🧠 Базовое время из ctx.departure_dt: {dt:%d.%m.%Y %H:%M}")
            return dt

        race_dt = self._parse_race_dt(ctx.race_name)
        if race_dt:
            self.log(f"🧠 Базовое время из race_name: {race_dt:%d.%m.%Y %H:%M}")
            return race_dt

        raise RuntimeError(f"Не удалось определить стартовое время отправления из race_name={ctx.race_name!r}")

    def _set_field(self, anchor_name: str, value: str, label: str, submit: bool = False, ctx=None):
        self.log(f"📝 {label}: {value}")
        point = None
        if ctx:
            point = ((ctx.state.get("ui_points") or {}).get(anchor_name) or None)

        if point:
            x, y = int(point["x"]), int(point["y"])
            self.session.click(x, y)
        else:
            self.session.click_anchor(anchor_name)

        self.session.sleep(0.08)
        self.session.press("f2")
        self.session.sleep(0.08)
        self.session.replace_current_field(value, submit=submit)
        self.session.sleep(0.15)

    def _apply_conflict(self, ctx, current_dt: datetime, finish_dt: datetime) -> tuple[datetime, bool]:
        candidate = finish_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

        self.log(f"⚠️ finish_dt={finish_dt:%d.%m.%Y %H:%M:%S}, "
                 f"candidate={candidate:%d.%m.%Y %H:%M}, "
                 f"current={current_dt:%d.%m.%Y %H:%M}"
                 )

        if candidate != current_dt:
            ctx.state["finish_dt"] = finish_dt
            ctx.state["suggested_departure_dt"] = candidate
            self.log(f"↪ Обновляю target departure -> {candidate:%d.%m.%Y %H:%M}")
            return candidate, True

        self.log("ℹ️ candidate совпадает с текущим временем — продолжаю ввод")
        return current_dt, False

    def _resolve_base_dt(self, ctx) -> datetime:
        suggested = ctx.state.get("suggested_departure_dt")
        if isinstance(suggested, datetime):
            self.log(f"🧠 Базовое время из suggested_departure_dt: {suggested:%d.%m.%Y %H:%М}")
            return suggested.replace(second=0, microsecond=0)

        if ctx.departure_dt:
            dt = self._parse_dt(ctx.departure_dt).replace(second=0, microsecond=0)
            self.log(f"🧠 Базовое время из ctx.departure_dt: {dt:%d.%m.%Y %H:%M}")
            return dt

        race_dt = self._parse_race_dt(ctx.race_name)
        if race_dt:
            self.log(f"🧠 Базовое время из race_name: {race_dt:%d.%m.%Y %H:%M}")
            return race_dt.replace(second=0, microsecond=0)

        raise RuntimeError(f"Не удалось определить базовое время отправления из race_name={ctx.race_name!r}")

    def _close_error_and_wait(self, timeout: float = 1.5, poll: float = 0.15):
        self.errors.close_error_dialog()
        self.session.sleep(0.2)

        waited = 0.0
        while waited < timeout:
            err = self.errors.detect()
            if not err:
                return
            self.session.sleep(poll)
            waited += poll

        raise RuntimeError("Диалог ошибки не закрылся вовремя")

    def _refocus_time_field(self):
        self.session.click_anchor("departure_time_field")
        self.session.sleep(0.15)
        self.session.click_anchor("departure_time_field")
        self.session.sleep(0.15)

    def _probe_departure_finish_dt(self, base_dt: datetime, max_attempts: int = 4) -> tuple[datetime | None, datetime]:
        last_probe_dt = base_dt.replace(second=0, microsecond=0)

        for attempt in range(1, max_attempts + 1):
            probe_dt = (base_dt - timedelta(days=(attempt - 1))).replace(second=0, microsecond=0)
            last_probe_dt = probe_dt
            probe_date = self._fmt_date(probe_dt)

            self.log(f"🧪 Probe attempt {attempt}: ставлю только дату {probe_date}")

            race_params_tab = self.session.ui_map.get_optional_anchor("race_params_tab")
            if race_params_tab:
                self.session.click(*race_params_tab)
                self.session.sleep(0.25)

            self._set_field("departure_date_field", probe_date, "Дата отправления (probe)", submit=False)

            self.session.click_anchor("departure_time_field")
            self.session.sleep(0.35)

            err = self.errors.detect()
            if err and err.kind == "date_conflict":
                if err.finish_dt:
                    self.log(f"✅ Probe поймал finish_dt={err.finish_dt:%d.%m.%Y %H:%M:%S}")
                    self._close_error_and_wait()
                    return err.finish_dt, last_probe_dt

                self.log("⚠️ Probe поймал date_conflict, но finish_dt не распарсился — пробую на день раньше")
                self._close_error_and_wait()
                continue

            if err:
                self._close_error_and_wait()
                raise RuntimeError(f"Неожиданная ошибка в probe: {err.kind}")

            self.log("ℹ️ Ошибки нет — пробую на день раньше")

        return None, last_probe_dt

    def _resolve_start_dt(self, ctx) -> datetime:
        suggested = ctx.state.get("suggested_departure_dt")
        if isinstance(suggested, datetime):
            return suggested.replace(second=0, microsecond=0)

        base_dt = self._resolve_base_dt(ctx)
        finish_dt, last_probe_dt = self._probe_departure_finish_dt(base_dt)

        if finish_dt:
            candidate = finish_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
            ctx.state["finish_dt"] = finish_dt
            ctx.state["suggested_departure_dt"] = candidate
            self.log(f"🧠 Probe дал suggested_departure_dt={candidate:%d.%m.%Y %H:%M}")
            return candidate

        ctx.state["suggested_departure_dt"] = last_probe_dt
        self.log("⚠️ Probe не поймал ошибку — использую самую дальнюю проверенную дату как fallback: "
                 f"{last_probe_dt:%d.%m.%Y %H:%M}")
        return last_probe_dt

    def run(self, ctx):
        state = self._ensure_state(ctx)

        skip, saved_departure = self._should_skip_by_saved_state(ctx)
        if skip:
            self._restore_saved_departure(ctx, saved_departure)
            return

        current_dt = self._resolve_start_dt(ctx)

        for round_idx in range(1, self.max_rounds + 1):
            self.log(f"\n=== FILL DEPARTURE ROUND {round_idx} ===")
            self.log(f"🎯 target={current_dt:%d.%m.%Y %H:%M}")

            race_params_tab = self.session.ui_map.get_optional_anchor("race_params_tab")
            if race_params_tab:
                self.session.click(*race_params_tab)
                self.session.sleep(0.35)

            self._set_field("departure_date_field",
                            self._fmt_date(current_dt),
                            "Дата отправления",
                            submit=False, ctx=ctx, )

            self._refocus_time_field()

            err = self.errors.detect()
            if err and err.kind == "date_conflict" and err.finish_dt:
                self.log("⚠️ Ошибка пересечения появилась после ввода даты / перехода в поле времени")
                self._close_error_and_wait()

                new_dt, changed = self._apply_conflict(ctx, current_dt, err.finish_dt)
                current_dt = new_dt

                if changed:
                    continue

            elif err:
                self._close_error_and_wait()
                raise RuntimeError(f"Ошибка после ввода даты: {err.kind}")

            self._refocus_time_field()
            self._set_field("departure_time_field",
                            self._fmt_time(current_dt),
                            "Время отправления",
                            submit=True,
                            ctx=ctx, )

            self.session.sleep(0.35)

            err = self.errors.detect()
            if err and err.kind == "date_conflict" and err.finish_dt:
                self.log("⚠️ Ошибка пересечения появилась после ввода времени")
                self._close_error_and_wait()

                new_dt, changed = self._apply_conflict(ctx, current_dt, err.finish_dt)
                current_dt = new_dt

                if changed:
                    continue

                raise RuntimeError("Ошибка пересечения повторилась с тем же временем после ввода времени")

            elif err:
                self._close_error_and_wait()
                raise RuntimeError(f"Ошибка после ввода времени: {err.kind}")

            ctx.departure_dt = current_dt.strftime("%d.%m.%Y %H:%M")
            state["final_departure_dt"] = current_dt
            state["suggested_departure_dt"] = current_dt

            progress = state.get("onec_progress")
            if not isinstance(progress, dict):
                progress = {}
                state["onec_progress"] = progress
            progress["departure_filled"] = True

            self.log(f"✅ Время отправления установлено: {ctx.departure_dt}")
            return

        raise RuntimeError("Не удалось подобрать корректную дату отправления")
