from Navigation_Bot.core.jSONManager import JSONManager
import re
import gspread
import os
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from Navigation_Bot.core.paths import INPUT_FILEPATH, CONFIG_JSON


class GoogleSheetsManager:
    def __init__(self, log_func=None):
        self.log = log_func
        self.config_manager = JSONManager(CONFIG_JSON)
        self.data_manager = JSONManager(INPUT_FILEPATH)

        self.sheet = None
        self.load_settings()

    def load_settings(self):
        data = self.config_manager.load_json()

        config_block = data.get("google_config", {})
        defaults = config_block.get("default", {})
        current = config_block.get("custom", defaults)

        self.creds_file = str(current.get("creds_file") or defaults.get("creds_file") or "")
        self.sheet_id = str(current.get("sheet_id") or defaults.get("sheet_id") or "")
        self.worksheet_index = int(current.get("worksheet_index") or defaults.get("worksheet_index") or 0)
        self.column_index = int(current.get("column_index") or defaults.get("column_index") or 0)

        if not os.path.exists(self.creds_file):
            self.log(f"❌ Файл авторизации не найден: {self.creds_file}")
            return

        try:
            # Загружаем JSON и достаём credentials
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
            sheet = client.open_by_key(self.sheet_id)
            self.sheet = sheet.get_worksheet(self.worksheet_index)

        except Exception as e:
            self.log(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.sheet = None

    def load_data(self):
        try:
            return self.sheet.get_all_values() if self.sheet else []
        except Exception as e:
            self.log(f"️ Ошибка загрузки данных с листа: {e}")
            return []

    def refresh_name(self, rows, file_path=None):
        file_path = file_path or self.file_path
        existing_data = self.data_manager.load_json(file_path)
        if not isinstance(existing_data, list):
            existing_data = []

        existing_indexes = {entry.get("index") for entry in existing_data}
        active_indexes = set()
        new_entries = []

        for i, row in enumerate(rows[2:], start=3):
            if len(row) < self.column_index or row[self.column_index - 1].strip() == "Готов":
                continue

            raw_ts = re.sub(r"\s+", "", row[3])  # убираем все пробелы из ТС
            number, phone = raw_ts[:9], raw_ts[9:]

            # Вставляем пробел перед регионом
            formatted_ts = number[:6] + ' ' + number[6:] if len(number) >= 9 else number

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
        filtered_data = [entry for entry in existing_data if entry.get("index") in active_indexes]

        result_data = filtered_data + new_entries

        self.data_manager.save_in_json(result_data, file_path)
        self.log(
            f"🔄 Обновление: добавлено {len(new_entries)}, удалено {len(existing_data) - len(filtered_data)} строк.")
        # return new_entries

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

    def write_all(self, items: list):
        if not items:
            self.log("⚠️ Нет данных для записи в Google Sheets.")
            return

        try:
            self.append_to_cell(items)
            self.log(f"📤 Обновлены все строки в Google Sheets ({len(items)} шт.)")
        except Exception as e:
            self.log(f"❌ Ошибка при записи в Google Sheets: {e}")
