import os
import re
from datetime import datetime, date

import gspread
from PyQt6.QtCore import QObject, pyqtSignal
from oauth2client.service_account import ServiceAccountCredentials

from Navigation_Bot.bots.dataCleaner import DataCleaner
from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import INPUT_FILEPATH, CONFIG_JSON
from Navigation_Bot.core.processedFlags import init_processed_flags


class GoogleSheetsManager(QObject):
    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self, config_key="default", log_func=None, parent=None, data_context=None):
        super().__init__(parent)
        self._external_log = log_func

        self.config_key = config_key
        self.config_manager = JSONManager(CONFIG_JSON)

        self.data_context = data_context or DataContext(str(INPUT_FILEPATH), log_func=log_func)

        # основные поля
        self.worksheet_index = None
        self.auth_sheet_id = None
        self.column_index = None
        self.file_path = None

        self.sheet = None
        self.load_settings()

    def _log(self, msg: str):
        """Безопасное логирование: только через сигнал"""
        text = str(msg)
        # внешний лог, если передан
        if self._external_log:
            try:
                self._external_log(text)
            except Exception:
                pass
        # сигнал для GUI
        self.log_message.emit(text)

    def _create_client(self):
        """Создаёт gspread-клиент из self.creds_file"""
        if not self.creds_file or not os.path.exists(self.creds_file):
            self._log(f"❌ Файл авторизации не найден: {self.creds_file}")
            return None

        try:
            full_block = JSONManager().load_json(self.creds_file)
            creds_data = full_block.get("credentials")
            if not creds_data:
                self._log(f"❌ В файле {self.creds_file} отсутствует ключ 'credentials'")
                return None

            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_data,
                scopes=["https://spreadsheets.google.com/feeds",
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive"])
            return gspread.authorize(creds)
        except Exception as e:
            self._log(f"❌ Ошибка создания клиента Google: {e}")
            return None

    def load_settings(self):
        data = self.config_manager.load_json()
        if not isinstance(data, dict):
            self._log("❌ config_manager.load_json() вернул не dict - проверь CONFIG_JSON")
            return

        config_block = data.get("google_config", {})
        defaults = config_block.get("default", {}) or {}
        custom = config_block.get("custom") or {}

        self.creds_file = str(custom.get("creds_file") or defaults.get("creds_file") or "")
        self.sheet_id = str(custom.get("sheet_id") or defaults.get("sheet_id") or "")
        self.auth_sheet_id = str(custom.get("auth_sheet_id") or defaults.get("auth_sheet_id") or "").strip()

        self.worksheet_index = int(custom.get("worksheet_index", defaults.get("worksheet_index", 0)) or 0)
        self.column_index = int(custom.get("column_index", defaults.get("column_index", 0)) or 0)

        self.file_path = str(custom.get("file_path") or defaults.get("file_path") or "").strip()

        client = self._create_client()
        if not client:
            return

        try:
            spreadsheet = client.open_by_key(self.sheet_id)
            self.spreadsheet = spreadsheet
            self._worksheets_cache = spreadsheet.worksheets()

            # если индекс вдруг вышел за границы
            if 0 <= self.worksheet_index < len(self._worksheets_cache):
                self.sheet = self._worksheets_cache[self.worksheet_index]
            else:
                self._log(f"⚠️ Некорректный worksheet_index={self.worksheet_index}, беру 0")
                self.worksheet_index = 0
                self.sheet = self._worksheets_cache[0]

        except Exception as e:
            print(f"❌ Ошибка подключения к Google Sheets: {e}")
            self._log(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.sheet = None

    def _get_account_sheet(self, title: str = "Account", sheet_id: str | None = None):
        """
        Ищет лист с аккаунтами по названию в отдельной таблице.
        sheet_id:
          - если передан явно -> используем его
          - иначе берем self.auth_sheet_id (из config.json)
          - если и его нет, падаем обратно на self.sheet_id (основная таблица)
        """
        # приоритет: аргумент -> auth_sheet_id -> основная sheet_id
        sheet_id = sheet_id or self.auth_sheet_id or self.sheet_id

        if not sheet_id:
            self._log("❌ Не указан ID таблицы для аккаунтов (auth_sheet_id/sheet_id).")
            return None

        spreadsheet = self._open_spreadsheet_by_id(sheet_id)
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

    def check_user_credentials(self, login: str,
                               password: str,
                               account_sheet_title: str = "Account",
                               sheet_id: str | None = None) -> tuple[bool, str]:
        """
        Проверяет логин/пароль по листу Account в таблице аккаунтов.

        sheet_id:
          - если передан явно -> использовать его
          - иначе берется self.auth_sheet_id (из config.json)
          - если и его нет, то self.sheet_id

        Также проверяет поле 'Time able' (если есть):
        - если дата в прошлом — доступ запрещён.
        """
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

            # индекс колонки с датой доступа (Time able), если она есть
            time_idx = header.index("time able") if "time able" in header else None

            for row in rows[1:]:
                if len(row) <= max(login_idx, pass_idx):
                    continue

                row_login = row[login_idx].strip()
                row_pass = row[pass_idx].strip()

                if row_login == login and row_pass == password:
                    #  1 проверка Time able
                    if time_idx is not None and time_idx < len(row):
                        time_val = (row[time_idx] or "").strip()
                        if time_val:
                            parsed_date = None
                            # поддерживаем несколько форматов дат
                            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                                try:
                                    parsed_date = datetime.strptime(time_val, fmt).date()
                                    break
                                except ValueError:
                                    continue

                            if parsed_date is None:
                                return False, f"Некорректный формат даты доступа: '{time_val}'."

                            today = date.today()
                            if today > parsed_date:
                                return False, f"Время доступа истекло ({time_val})."

                    #  2 проверка active
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

    def _open_spreadsheet_by_id(self, sheet_id: str):
        """Открыть любую таблицу по ее ID, используя тот же creds_file."""
        if not sheet_id:
            self._log("❌ Не указан ID таблицы для авторизации.")
            return None

        client = self._create_client()
        if not client:
            return None

        try:
            return client.open_by_key(sheet_id)
        except Exception as e:
            self._log(f"❌ Ошибка открытия таблицы по ID '{sheet_id}': {e}")
            return None

    def list_worksheets(self):
        """Возвращает список листов: [{'title': str, 'index': int}, ...]"""
        try:
            if not getattr(self, "spreadsheet", None):
                return []
            result = []
            for ws in self.spreadsheet.worksheets():
                # ws.index у gspread 0-based, как у get_worksheet()
                result.append({"title": ws.title, "index": ws.index})
            return result
        except Exception as e:
            print(f"⚠️ Не удалось получить список листов: {e}")
            self._log(f"⚠️ Не удалось получить список листов: {e}")
            return []

    def set_active_worksheet(self, index: int):
        """Быстро переключает активный лист, без обращений к Google"""
        try:
            cache = getattr(self, "_worksheets_cache", None)
            if not cache:
                print("⚠️ Листы ещё не загружены (нет _worksheets_cache).")
                self._log("⚠️ Листы ещё не загружены (нет _worksheets_cache).")
                return

            if not (0 <= index < len(cache)):
                print(f"⚠️ Некорректный индекс листа: {index}")
                self._log(f"⚠️ Некорректный индекс листа: {index}")
                return

            # просто берем из кэша - локальная операция, без сети
            self.sheet = cache[index]
            self.worksheet_index = index

            # сохраняем выбор в config.custom
            cfg = self.config_manager.load_json() or {}
            gcfg = cfg.setdefault("google_config", {})
            custom = gcfg.setdefault("custom", {})
            custom["worksheet_index"] = index
            self.config_manager.save_in_json(cfg)

            self._log(f"✅ Активный лист: {self.sheet.title}")
        except:
            print("set_active_worksheet")

    def pull_to_context(self, data_context, input_filepath: str | None = None):
        try:
            rows = self.load_data()

            if not rows:
                msg = "Загрузка отменена: нет данных из Google (ошибка/пусто)."
                self._log(f"⚠️ {msg}")
                return False, msg

            self.data_context = data_context or self.data_context
            self.refresh_name(rows, update_existing=False)

            cleaner = DataCleaner(data_context=data_context, log_func=self._log)
            cleaner.start_clean()

            if self.data_context:
                self.data_context.reload()
                clean_data = self.data_context.get() or []
                init_processed_flags(clean_data, clean_data, loads_key="Выгрузка")
                self.data_context.set(clean_data)
            return True, None

        except Exception as e:
            self._log(f"❌ pull_to_context: {e}")
            return False, str(e)

    def pull_to_context_async(self, data_context, input_filepath: str, executor):
        try:
            # self._log("📥 Загрузка данных из Google Sheets...")
            self.started.emit()

            def task():
                ok, err = self.pull_to_context(data_context, input_filepath)
                if ok:
                    self.finished.emit()
                else:
                    self.error.emit(err or "Unknown error")

            executor.submit(task)
        except Exception as e:
            self._log(f"❌ pull_to_context_async: {e}")

    def load_data(self):
        """
        Грузим только строки, где:
          1) в колонке M НЕ 'Готов'
          2) хотя бы одна из D/E/F/G/H не пустая.
        При этом тянем только диапазоны D3:H и M3:M, а не весь лист.
        Возвращаем dict: {row_index: [D, E, F, G, H]}.
        """
        try:
            if not self.sheet:
                self._log("⚠️ Лист Google Sheets не инициализирован - пропускаю загрузку")
                return None

            # Берём 2 диапазона: D3:H и M3:M
            ranges = ["D3:H", "M3:M"]
            values_list = self.sheet.batch_get(ranges, major_dimension="ROWS")
            d_to_h_rows = values_list[0] if len(values_list) > 0 else []
            m_rows = values_list[1] if len(values_list) > 1 else []

            if not d_to_h_rows:
                self._log("⚠️ Таблица пуста или слишком короткая - обновление отменено.")
                return None

            result = {}

            for offset, dh in enumerate(d_to_h_rows):
                # Фактический номер строки в листе (учитываем, что начали с 3-й)
                row_index = 3 + offset

                # Столбец M
                m_val = ""
                if offset < len(m_rows) and m_rows[offset]:
                    m_val = (m_rows[offset][0] or "").strip()

                # M == "Готов" -> пропускаем
                if m_val == "Готов":
                    continue

                # Столбцы D..H
                d = (dh[0] or "").strip() if len(dh) > 0 and dh[0] else ""
                e = (dh[1] or "").strip() if len(dh) > 1 and dh[1] else ""
                f = (dh[2] or "").strip() if len(dh) > 2 and dh[2] else ""
                g = (dh[3] or "").strip() if len(dh) > 3 and dh[3] else ""
                h = (dh[4] or "").strip() if len(dh) > 4 and dh[4] else ""

                # если все D..H пустые - пропускаем
                if not any([d, e, f, g, h]):
                    continue

                # Оставляем только нужное: D..H, привязанные к реальному row_index
                result[row_index] = [d, e, f, g, h]

            if not result:
                self._log("↩️ В листе не найдено подходящих строк (M≠'Готов' и есть данные в D–H)")
                return None

            return result

        except Exception as e:
            self._log(f"️❌ Ошибка загрузки данных с листа: {e}")
            return None

    def refresh_name(self, rows, file_path=None, update_existing: bool = False):
        updated_count = 0

        try:
            if not rows:
                self._log("↩️ Обновление отменено: нет данных (ошибка/пустой лист). Текущее состояние сохранено")
                return

            ctx = self.data_context
            existing_data = (ctx.get() or []) if ctx else (JSONManager().load_json(file_path or self.file_path) or [])
            existing_indexes = {entry.get("index") for entry in existing_data if isinstance(entry, dict)}
            by_index = {entry.get("index"): entry for entry in existing_data if isinstance(entry, dict)}
            active_indexes, new_entries = set(), []

            # если rows пришёл как dict {row_index: [D,E,F,G,H]}
            if isinstance(rows, dict):
                for i, dh in rows.items():
                    # dh = [D, E, F, G, H]
                    d = dh[0] if len(dh) > 0 else ""
                    e = dh[1] if len(dh) > 1 else ""
                    f = dh[2] if len(dh) > 2 else ""
                    g = dh[3] if len(dh) > 3 else ""
                    h = dh[4] if len(dh) > 4 else ""

                    raw_ts = re.sub(r"\s+", "", d)  # ТС+телефон
                    number, phone = raw_ts[:9], raw_ts[9:]
                    formatted_ts = number[:6] + ' ' + number[6:] if len(number) >= 9 else number

                    fio = e
                    load = g
                    unload = h

                    # Доп. защита: пропускаем полностью пустые строки
                    if not any([formatted_ts, phone, fio, load, unload]):
                        continue

                    active_indexes.add(i)

                    fresh = {"index": i,
                             "ТС": formatted_ts,
                             "Телефон": phone,
                             "ФИО": fio,
                             "КА": f,
                             "Погрузка": load,
                             "Выгрузка": unload, }

                    if i in existing_indexes:
                        if update_existing:
                            old = by_index.get(i)
                            updated_count += 1
                            if old is not None:
                                old.update(fresh)
                                old["raw_load"] = load
                                old["raw_unload"] = unload
                                old["Погрузка"] = load
                                old["Выгрузка"] = unload

                    else:
                        new_entries.append(fresh)



            # старый режим - если load_data ещё вернёт полный лист
            else:
                for i, row in enumerate(rows[2:], start=3):
                    if len(row) < self.column_index or row[self.column_index - 1].strip() == "Готов":
                        continue

                    raw_ts = re.sub(r"\s+", "", row[3])  # убираем все пробелы из ТС
                    number, phone = raw_ts[:9], raw_ts[9:]
                    formatted_ts = number[:6] + ' ' + number[6:] if len(number) >= 9 else number

                    fio = row[4] if len(row) > 4 else ""
                    load = row[6] if len(row) > 6 else ""
                    unload = row[7] if len(row) > 7 else ""

                    if not any([formatted_ts, phone, fio, load, unload]):
                        continue

                    active_indexes.add(i)

                    fresh = {"index": i,
                             "ТС": formatted_ts,
                             "Телефон": phone,
                             "ФИО": fio,
                             "КА": row[5] if len(row) > 5 else "",
                             "Погрузка": load,
                             "Выгрузка": unload, }

                    if i in existing_indexes:
                        old = by_index.get(i)
                        if old is not None:
                            old.update(fresh)
                            old["raw_load"] = load
                            old["raw_unload"] = unload
                            old["Погрузка"] = load
                            old["Выгрузка"] = unload
                        self._log(f"✅ Обновил существующую строку index={i}")

                    else:
                        new_entries.append(fresh)

            if not active_indexes and not new_entries:
                self._log("↩️ В листе не найдено активных строк. Обновление пропущено, данные не изменены.")
                return

            # update_existing=True означает "точечный overwrite", а не "синхронизация списка".
            if update_existing:
                # existing_data уже обновлён "на месте" через old.update(...)
                # поэтому просто сохраняем весь массив + добавляем новые (если вдруг index не существовал)
                result_data = existing_data + new_entries
                deleted_count = 0
            else:
                # режим синхронизации (как раньше)
                filtered_data = [e for e in existing_data if e.get("index") in active_indexes]
                result_data = filtered_data + new_entries
                deleted_count = len(existing_data) - len(filtered_data)

            if ctx:
                ctx.set(result_data)
            else:
                JSONManager().save_in_json(result_data, file_path or self.file_path)

            self._log(
                f"🔄 Обновление: обновлено {updated_count}, добавлено {len(new_entries)}, удалено {deleted_count} строк.")

        except Exception as e:
            self._log(f"❌ refresh_name error: {e}")

    def append_to_cell(self, data, column=12):
        # self._log(f"GSHEET append => sheet_id={self.sheet_id}, ws_index={self.worksheet_index}, col={column}")

        if isinstance(data, list):
            for item in data:
                self._append_entry(item, column)
        elif isinstance(data, dict):
            self._append_entry(data, column)

    def _append_entry(self, item, column):
        try:
            if not self.sheet:
                self._log("⚠️ Лист Google Sheets не инициализирован")
                return

            row_index = item.get("index")
            if not row_index:
                self._log("⚠️ Пропуск записи: нет индекса строки")
                return

            current_time = datetime.now().strftime("%d-%m %H:%M")

            geo = item.get("гео") or ""
            coor = item.get("коор") or ""
            speed = item.get("скорость")

            if geo == "нет навигации":
                new_text = f"{current_time} нет навигации"
            elif not geo and not coor:
                self._log(f"⚠️ Пропуск строки {row_index}: нет гео/координат")
                return
            else:
                status = "стоит" if isinstance(speed, (int, float)) and speed < 5 else "едет"
                new_text = f"{current_time} {status} {geo}{' ' + coor if coor else ''}"

            try:
                cell_value = self.sheet.cell(row_index, column).value
            except Exception as e:
                self._log(f"⚠️ Не удалось прочитать ячейку {row_index}, кол. {column}: {e}")
                cell_value = ""

            updated_value = f"{cell_value}\n{new_text}" if cell_value else new_text
            self.sheet.update_cell(row_index, column, updated_value)
            self._log(f"✅ Обновлена строка {row_index}, колонка {column}")

        except Exception as e:
            self._log(f"❌ Ошибка при записи строки {item.get('ТС')}: {e}")

    def is_row_empty(self, row_index: int) -> bool:
        """Проверяет, пустая ли строка в колонках 1–7"""
        try:
            values = self.sheet.row_values(row_index)
            return all((i >= len(values) or not values[i].strip()) for i in range(7))
        except Exception:
            return True  # если ошибки чтения - считаем пустой

    def upload_new_row(self, entry: dict):
        """Выгружает новую запись в Google Sheets"""
        try:
            row_index = entry["index"]
            ts_with_phone = f"{entry.get('ТС', '')} {entry.get('Телефон', '')}".strip()

            load_str = "; ".join(f"{blk.get(f'Время {i + 1}', '')} {blk.get(f'Погрузка {i + 1}', '')}".strip()
                                 for i, blk in enumerate(entry.get("Погрузка", [])))

            unload_str = "; ".join(f"{blk.get(f'Время {i + 1}', '')} {blk.get(f'Выгрузка {i + 1}', '')}".strip()
                                   for i, blk in enumerate(entry.get("Выгрузка", [])))

            row_data = [ts_with_phone,       # col D (ТС + телефон)
                        entry.get("ФИО", ""),# col E (ФИО)
                        entry.get("КА", ""), # col F (КА)
                        load_str,            # col G (Погрузка)
                        unload_str]          # col H (Выгрузка)

            self.sheet.update(f"D{row_index}:H{row_index}", [row_data])
            self._log(f"📤 Новая запись отправлена в Google Sheets (row={row_index})")
        except Exception as e:
            self._log(f"❌ Ошибка выгрузки новой строки: {e}")

    def write_all(self, items: list):
        if not items:
            self._log("⚠️ Нет данных для записи в Google Sheets")
            return

        try:
            self.append_to_cell(items)
            self._log(f"📤 Обновлены все строки в Google Sheets ({len(items)} шт.)")
        except Exception as e:
            self._log(f"❌ Ошибка при записи в Google Sheets: {e}")
