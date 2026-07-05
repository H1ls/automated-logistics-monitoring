from __future__ import annotations

from datetime import date, datetime


from Navigation_Bot.core.logging import noop_log, normalize_log_func


class GoogleAccountAuthService:
    def __init__(self, gsheet, log=None):
        self.gsheet = gsheet
        self.log = normalize_log_func(log or noop_log)

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)
        elif hasattr(self.gsheet, "_log"):
            self.gsheet._log(msg)

    def _get_account_sheet(self, title: str = "Account", sheet_id: str | None = None):
        sheet_id = sheet_id or getattr(self.gsheet, "auth_sheet_id", "") or getattr(self.gsheet, "sheet_id", "")

        if not sheet_id:
            self._log("❌ Не указан ID таблицы для аккаунтов (auth_sheet_id/sheet_id).")
            return None

        spreadsheet = self.gsheet.open_spreadsheet_by_id(sheet_id)
        if not spreadsheet:
            self._log("❌ Не удалось открыть таблицу с аккаунтами (проверь auth_sheet_id).")
            return None

        try:
            for ws in spreadsheet.worksheets():
                if ws.title.strip().lower() == title.strip().lower():
                    return ws

            self._log(f"⚠️ Лист '{title}' не найден в таблице с аккаунтами.")
            return None
        except Exception as e:
            self._log(f"❌ Ошибка поиска листа '{title}' в таблице аккаунтов: {e}")
            return None

    def check_user_credentials(
        self,
        login: str,
        password: str,
        account_sheet_title: str = "Account",
        sheet_id: str | None = None,
    ) -> tuple[bool, str]:
        login = (login or "").strip()
        password = (password or "").strip()

        if not login or not password:
            return False, "Введите логин и пароль."

        ws = self._get_account_sheet(account_sheet_title, sheet_id=sheet_id)
        if ws is None:
            return False, f"Лист '{account_sheet_title}' не найден или нет доступа к таблице аккаунтов."

        try:
            rows = ws.get_all_values()
            if not rows or len(rows) < 2:
                return False, "Лист аккаунтов пуст или слишком короткий."

            header = [c.strip().lower() for c in rows[0]]
            try:
                login_idx = header.index("login")
                pass_idx = header.index("password")
            except ValueError:
                return False, "В листе аккаунтов нет колонок 'login'/'password'."

            time_idx = header.index("time able") if "time able" in header else None

            for row in rows[1:]:
                if len(row) <= max(login_idx, pass_idx):
                    continue

                row_login = row[login_idx].strip()
                row_pass = row[pass_idx].strip()

                if row_login != login or row_pass != password:
                    continue

                if time_idx is not None and time_idx < len(row):
                    time_val = (row[time_idx] or "").strip()
                    if time_val:
                        parsed_date = self._parse_access_date(time_val)
                        if parsed_date is None:
                            return False, f"Некорректный формат даты доступа: '{time_val}'."

                        if date.today() > parsed_date:
                            return False, f"Время доступа истекло ({time_val})."

                active_idx = header.index("active") if "active" in header else None
                if active_idx is not None and active_idx < len(row):
                    active_val = (row[active_idx] or "").strip()
                    if active_val and active_val not in ("1", "true", "True", "да", "Да"):
                        return False, "Учетная запись отключена."

                self._log(f"✅ Успешный вход: {login}")
                return True, ""

            return False, "Неверный логин или пароль."
        except Exception as e:
            self._log(f"❌ Ошибка проверки логина: {e}")
            return False, f"Ошибка доступа к таблице аккаунтов: {e}"

    def _parse_access_date(self, value: str) -> date | None:
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None
