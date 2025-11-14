import re
import os
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from PyQt6.QtCore import QObject, pyqtSignal

from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import INPUT_FILEPATH, CONFIG_JSON
from Navigation_Bot.bots.dataCleaner import DataCleaner
from Navigation_Bot.core.processedFlags import init_processed_flags


class GoogleSheetsManager(QObject):
    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, config_key="default", log_func=None, parent=None, data_context=None):
        super().__init__(parent)
        self.log = log_func
        self.config_key = config_key
        self.config_manager = JSONManager(CONFIG_JSON)
        self.data_manager = JSONManager(INPUT_FILEPATH)

        self.data_context = data_context or DataContext(str(INPUT_FILEPATH), log_func=log_func)

        # основные поля
        self.creds_path = None
        self.sheet_id = None
        self.worksheet_index = None
        self.column_index = None
        self.file_path = None

        self.sheet = None
        self.load_settings()

    def load_settings(self):
        data = self.config_manager.load_json()
        if not isinstance(data, dict):
            self.log("❌ config_manager.load_json() вернул не dict - проверь CONFIG_JSON")
            return

        config_block = data.get("google_config", {})
        defaults = config_block.get("default", {}) or {}
        custom = config_block.get("custom") or {}

        self.creds_file = str(custom.get("creds_file") or defaults.get("creds_file") or "")
        self.sheet_id = str(custom.get("sheet_id") or defaults.get("sheet_id") or "")

        if "worksheet_index" in custom:
            self.worksheet_index = int(custom["worksheet_index"])
        else:
            self.worksheet_index = int(defaults.get("worksheet_index") or 0)

        if "column_index" in custom:
            self.column_index = int(custom["column_index"])
        else:
            self.column_index = int(defaults.get("column_index") or 0)

        self.file_path = str(custom.get("file_path") or defaults.get("file_path") or "").strip()

        if not os.path.exists(self.creds_file):
            self.log(f"❌ Файл авторизации не найден: {self.creds_file}")
            return

        try:
            full_block = JSONManager().load_json(self.creds_file)
            creds_data = full_block.get("credentials")

            if not creds_data:
                self.log(f"❌ В файле {self.creds_file} отсутствует ключ 'credentials'")
                return

            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_data,
                scopes=[
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )

            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(self.sheet_id)

            # сохраняем кэш всех листов
            self.spreadsheet = spreadsheet
            self._worksheets_cache = spreadsheet.worksheets()

            # если индекс вдруг вышел за границы
            if 0 <= self.worksheet_index < len(self._worksheets_cache):
                self.sheet = self._worksheets_cache[self.worksheet_index]
            else:
                self.log(f"⚠️ Некорректный worksheet_index={self.worksheet_index}, беру 0")
                self.worksheet_index = 0
                self.sheet = self._worksheets_cache[0]


        except Exception as e:
            self.log(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.sheet = None

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
            if self.log:
                self.log(f"⚠️ Не удалось получить список листов: {e}")
            return []

    def set_active_worksheet(self, index: int):
        """Быстро переключает активный лист, без обращений к Google."""

        cache = getattr(self, "_worksheets_cache", None)
        if not cache:
            if self.log:
                self.log("⚠️ Листы ещё не загружены (нет _worksheets_cache).")
            return

        if not (0 <= index < len(cache)):
            if self.log:
                self.log(f"⚠️ Некорректный индекс листа: {index}")
            return

        # просто берем из кэша - это локальная операция, без сети
        self.sheet = cache[index]
        self.worksheet_index = index

        # сохраняем выбор в config.custom
        cfg = self.config_manager.load_json() or {}
        gcfg = cfg.setdefault("google_config", {})
        custom = gcfg.setdefault("custom", {})
        custom["worksheet_index"] = index
        self.config_manager.save_in_json(cfg)

        if self.log:
            self.log(f"📄 Активный лист: {self.sheet.title} (index={index})")

    def pull_to_context(self, data_context, input_filepath: str | None = None):
        try:
            rows = self.load_data()
            if not rows:
                msg = "Загрузка отменена: нет данных из Google (ошибка/пусто)."
                if self.log: self.log(f"⚠️ {msg}")
                return False, msg

            self.data_context = data_context or self.data_context
            self.refresh_name(rows)
            cleaner = DataCleaner(data_context=data_context, log_func=self.log)
            cleaner.start_clean()

            if self.data_context:
                self.data_context.reload()
                clean_data = self.data_context.get() or []
                init_processed_flags(clean_data, clean_data, loads_key="Выгрузка")
                self.data_context.set(clean_data)

            return True, None
        except Exception as e:
            if self.log: self.log(f"❌ pull_to_context: {e}")
            return False, str(e)

    def pull_to_context_async(self, data_context, input_filepath: str, executor):
        self.log("📥 Загрузка данных из Google Sheets...")
        self.started.emit()

        def task():
            ok, err = self.pull_to_context(data_context, input_filepath)
            if ok:
                self.finished.emit()
            else:
                self.error.emit(err or "Unknown error")

        executor.submit(task)

    def load_data(self):
        try:
            if not self.sheet:
                self.log("⚠️ Лист Google Sheets не инициализирован - пропускаю загрузку.")
                return None
            rows = self.sheet.get_all_values()
            if not rows or len(rows) < 3:
                self.log("⚠️ Таблица пуста или слишком короткая - обновление отменено.")
                return None
            return rows
        except Exception as e:
            self.log(f"️❌ Ошибка загрузки данных с листа: {e}")
            return None

    def refresh_name(self, rows, file_path=None):  # Возможно перенести в dataCleaner
        if not rows:
            self.log("↩️ Обновление отменено: нет данных (ошибка загрузки/пустой лист). Текущее состояние сохранено.")
            return

        ctx = self.data_context
        if ctx:
            existing_data = ctx.get() or []
        else:
            target_path = file_path or self.file_path
            existing_data = JSONManager().load_json(target_path) or []

        existing_indexes = {entry.get("index") for entry in existing_data}
        active_indexes, new_entries = set(), []

        for i, row in enumerate(rows[2:], start=3):
            if len(row) < self.column_index or row[self.column_index - 1].strip() == "Готов":
                continue

            raw_ts = re.sub(r"\s+", "", row[3])  # убираем все пробелы из ТС
            number, phone = raw_ts[:9], raw_ts[9:]
            formatted_ts = number[:6] + ' ' + number[6:] if len(number) >= 9 else number  # пробел перед регионом

            fio = row[4] if len(row) > 4 else ""
            load = row[6] if len(row) > 6 else ""
            unload = row[7] if len(row) > 7 else ""

            #  Пропуск полностью пустых строк
            if not any([formatted_ts, phone, fio, load, unload]):
                continue

            active_indexes.add(i)
            if i not in existing_indexes:
                new_entries.append({
                    "index": i,
                    "ТС": formatted_ts,
                    "Телефон": phone,
                    "ФИО": row[4],
                    "КА": row[5],
                    "Погрузка": row[6],
                    "Выгрузка": row[7],
                })
        if not active_indexes and not new_entries:
            self.log("↩️ В листе не найдено активных строк. Обновление пропущено, данные не изменены.")
            return

        filtered_data = [entry for entry in existing_data if entry.get("index") in active_indexes]
        result_data = filtered_data + new_entries

        if ctx:
            ctx.set(result_data)
        else:
            target_path = file_path or self.file_path
            JSONManager().save_in_json(result_data, target_path)
        self.log(
            f"🔄 Обновление: добавлено {len(new_entries)}, удалено {len(existing_data) - len(filtered_data)} строк.")

    def append_to_cell(self, data, column=12):
        if isinstance(data, list):
            for item in data:
                self._append_entry(item, column)
        elif isinstance(data, dict):
            self._append_entry(data, column)

    def _append_entry(self, item, column):
        try:
            if not self.sheet:
                self.log("⚠️ Лист Google Sheets не инициализирован.")
                return

            row_index = item.get("index")
            if not row_index:
                self.log("⚠️ Пропуск записи: нет индекса строки.")
                return

            geo = item.get("гео", "")
            coor = item.get("коор", "")
            if not geo and not coor:
                self.log(f"⚠️ Пропуск строки {row_index}: нет гео/координат.")
                return

            current_time = datetime.now().strftime("%d-%m %H:%M")
            speed = item.get("скорость", 0)
            status = "стоит" if isinstance(speed, (int, float)) and speed < 5 else "едет"
            new_text = f"{current_time} {status} {geo} {coor}"

            try:
                cell_value = self.sheet.cell(row_index, column).value
            except Exception as e:
                self.log(f"⚠️ Не удалось прочитать ячейку {row_index}, кол. {column}: {e}")
                cell_value = ""

            updated_value = f"{cell_value}\n{new_text}" if cell_value else new_text
            self.sheet.update_cell(row_index, column, updated_value)
            self.log(f"✅ Обновлена строка {row_index}, колонка {column}")

        except Exception as e:
            self.log(f"❌ Ошибка при записи строки {item.get('ТС')}: {e}")

    def is_row_empty(self, row_index: int) -> bool:
        """Проверяет, пустая ли строка в колонках 1–7"""
        try:
            values = self.sheet.row_values(row_index)
            return all((i >= len(values) or not values[i].strip()) for i in range(7))
        except Exception:
            return True  # если ошибки чтения — считаем пустой

    def upload_new_row(self, entry: dict):
        """Выгружает новую запись в Google Sheets"""
        try:
            row_index = entry["index"]
            ts_with_phone = f"{entry.get('ТС', '')} {entry.get('Телефон', '')}".strip()

            load_str = "; ".join(
                f"{blk.get(f'Время {i + 1}', '')} {blk.get(f'Погрузка {i + 1}', '')}".strip()
                for i, blk in enumerate(entry.get("Погрузка", []))
            )
            unload_str = "; ".join(
                f"{blk.get(f'Время {i + 1}', '')} {blk.get(f'Выгрузка {i + 1}', '')}".strip()
                for i, blk in enumerate(entry.get("Выгрузка", []))
            )

            row_data = [
                ts_with_phone,         # col D (ТС + телефон)
                entry.get("ФИО", ""),  # col E (ФИО)
                entry.get("КА", ""),   # col F (КА)
                load_str,              # col G (Погрузка)
                unload_str             # col H (Выгрузка)
            ]

            self.sheet.update(f"D{row_index}:H{row_index}", [row_data])
            self.log(f"📤 Новая запись отправлена в Google Sheets (row={row_index})")
        except Exception as e:
            self.log(f"❌ Ошибка выгрузки новой строки: {e}")

    def write_all(self, items: list):
        if not items:
            self.log("⚠️ Нет данных для записи в Google Sheets.")
            return

        try:
            self.append_to_cell(items)
            self.log(f"📤 Обновлены все строки в Google Sheets ({len(items)} шт.)")
        except Exception as e:
            self.log(f"❌ Ошибка при записи в Google Sheets: {e}")
