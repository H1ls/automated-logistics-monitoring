from Navigation_Bot.jSONManager import JSONManager
import re
import gspread
import logging
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials


class GoogleSheetsManager:
    def __init__(self, creds_file="config/Credentials_wialon.json",
                 sheet_id="1uz2ZXlCBltsD8s96GNuQELDEJ5_qCBuDFP2dvxeNqsU",
                 worksheet_index=3, column_index=14,
                 file_path="config/selected_data.json",log_func = None):
        self.log = log_func or print
        self.creds_file = creds_file
        self.sheet_id = sheet_id
        self.worksheet_index = worksheet_index
        self.column_index = column_index
        self.file_path = file_path
        self.json_manager = JSONManager()

        try:
            self.creds = Credentials.from_service_account_file(
                self.creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            self.client = gspread.authorize(self.creds)
            self.sheet = self.client.open_by_key(self.sheet_id).get_worksheet(self.worksheet_index)
        except Exception as e:
            self.log(f" Ошибка при подключении к Google Sheets: {e}")
            self.sheet = None

    def append_to_cell(self, path, column=13):
        data = self.json_manager.load_json(path)
        if isinstance(data, list):
            for item in data:
                self._append_entry(item, column)
        elif isinstance(data, dict):
            self._append_entry(data, column)

    def _append_entry(self, item, column):
        try:
            if not self.sheet:
                return
            row_index = item.get("index")
            if not row_index:
                self.log(" Нет индекса строки")
                return
            geo = item.get("гео", "")
            coor = item.get("коор", "")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_text = f"{current_time}, едет, {geo}, {coor}"

            cell_value = self.sheet.cell(row_index, column).value
            updated_value = f"{cell_value}\n{new_text}" if cell_value else new_text
            self.sheet.update_cell(row_index, column, updated_value)
            self.log(f" Обновлена строка {row_index}, колонка {column}")
        except Exception as e:
            self.log(f" Ошибка обновления ячейки: {e}")

    def load_data(self):
        try:
            return self.sheet.get_all_values() if self.sheet else []
        except Exception as e:
            self.log(f"️ Ошибка загрузки данных с листа: {e}")
            return []

    def refresh_name(self, rows, file_path=None):
        file_path = file_path or self.file_path
        existing_data = self.json_manager.load_json(file_path) or []
        existing_indexes = {entry.get("index") for entry in existing_data}
        new_entries = []

        for i, row in enumerate(rows[2:], start=3):
            if len(row) < self.column_index or row[self.column_index - 1].strip() != "Готов":
                raw_ts = re.sub(r"\s+", "", row[3])  # убираем все пробелы из ТС
                number, phone = raw_ts[:9], raw_ts[9:]

                # Вставляем пробел перед регионом
                formatted_ts = number[:6] + ' ' + number[6:] if len(number) >= 9 else number

                if i not in existing_indexes:
                    new_entries.append({
                        "index": i,
                        "ТС": formatted_ts,
                        "Телефон": phone,
                        "ФИО": row[5],
                        "Погрузка": row[7],
                        "Выгрузка": row[8],
                    })

        self.json_manager.save_json(existing_data + new_entries, file_path)
        self.log(f"Обновлено: добавлено {len(new_entries)} новых записей.")

