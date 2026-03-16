# LogistX/onec/steps/fill_departure.py
from __future__ import annotations

import re
from datetime import datetime, timedelta


class FillDepartureStep:
    stage = "fill_departure"

    def __init__(self, session, errors, log_func=print, max_rounds: int = 5):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.max_rounds = max_rounds

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        self.log(f"Parsing {value}")
        value = (value or "").strip()
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        raise ValueError(f"Не удалось распарсить datetime: {value!r}")

    @staticmethod
    def _parse_race_dt(race_name: str) -> datetime | None:
        """
        'Рейс (уэ) ВТ000002438 от 07.03.2026 19:38:35' -> datetime(2026, 3, 7, 19, 38)
        """
        m = re.search(r"от\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})(?::\d{2})?", race_name or "")
        if not m:
            return None
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M")

    @staticmethod
    def _fmt_date(dt: datetime) -> str:
        return dt.strftime("%d.%m.%Y")

    @staticmethod
    def _fmt_time(dt: datetime) -> str:
        return dt.strftime("%H:%M")

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

        raise RuntimeError("Не удалось определить стартовое время отправления")

    def _set_field(self, anchor_name: str, value: str, label: str, submit: bool = False):
        self.log(f"📝 {label}: {value}")
        self.session.click_anchor(anchor_name)
        self.session.sleep(0.08)
        self.session.press("f2")
        self.session.sleep(0.08)
        self.session.replace_current_field(value, submit=submit)

    def _apply_conflict(self, ctx, current_dt: datetime, finish_dt: datetime) -> tuple[datetime, bool]:
        candidate = finish_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

        self.log(f"⚠️ finish_dt={finish_dt:%d.%m.%Y %H:%M:%S}, "
                 f"candidate={candidate:%d.%m.%Y %H:%M}, "
                 f"current={current_dt:%d.%m.%Y %H:%M}")

        if candidate != current_dt:
            ctx.state["finish_dt"] = finish_dt
            ctx.state["suggested_departure_dt"] = candidate
            self.log(f"↪ Обновляю target departure -> {candidate:%d.%m.%Y %H:%M}")
            return candidate, True

        self.log("ℹ️ candidate совпадает с текущим временем — продолжаю ввод")
        return current_dt, False

    def run(self, ctx):
        current_dt = self._resolve_initial_dt(ctx)

        for round_idx in range(1, self.max_rounds + 1):
            self.log(f"\n=== FILL DEPARTURE ROUND {round_idx} ===")
            self.log(f"🎯 target={current_dt:%d.%m.%Y %H:%M}")

            # 1. вкладка параметров рейса
            race_params_tab = self.session.ui_map.get_optional_anchor("race_params_tab")
            if race_params_tab:
                self.session.click(*race_params_tab)
                self.session.sleep(0.35)

            # 2. ввод даты
            self._set_field("departure_date_field", self._fmt_date(current_dt), "Дата отправления", submit=False, )

            # 3. переход в поле времени
            self.session.click_anchor("departure_time_field")
            self.session.sleep(0.25)

            err = self.errors.detect()
            if err and err.kind == "date_conflict" and err.finish_dt:
                self.log("⚠️ Ошибка пересечения появилась после ввода даты / перехода в поле времени")
                self.errors.close_error_dialog()

                new_dt, changed = self._apply_conflict(ctx, current_dt, err.finish_dt)
                current_dt = new_dt

                if changed:
                    continue

            elif err:
                self.errors.close_error_dialog()
                raise RuntimeError(f"Ошибка после ввода даты: {err.kind}")

            # 4. ввод времени
            self._set_field("departure_time_field",
                            self._fmt_time(current_dt),
                            "Время отправления",
                            submit=True, )
            self.session.sleep(0.35)

            err = self.errors.detect()
            if err and err.kind == "date_conflict" and err.finish_dt:
                self.log("⚠️ Ошибка пересечения появилась после ввода времени")
                self.errors.close_error_dialog()

                new_dt, changed = self._apply_conflict(ctx, current_dt, err.finish_dt)
                current_dt = new_dt

                if changed:
                    continue

                raise RuntimeError("Ошибка пересечения повторилась с тем же временем после ввода времени")

            elif err:
                self.errors.close_error_dialog()
                raise RuntimeError(f"Ошибка после ввода времени: {err.kind}")

            ctx.departure_dt = current_dt.strftime("%d.%m.%Y %H:%M")
            ctx.state["final_departure_dt"] = current_dt
            self.log(f"✅ Время отправления установлено: {ctx.departure_dt}")
            return

        raise RuntimeError("Не удалось подобрать корректную дату отправления")
