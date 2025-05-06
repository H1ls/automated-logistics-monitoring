from config.requirements import *
from json_manager import JSONManager
import json


class GoogleSheetsManager:
    def __init__(self, config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        google_sheets_config = config["google_sheets"]
        json_paths = config["json_paths"]

        self.creds_file = google_sheets_config["creds_file"]
        self.sheet_id = google_sheets_config["sheet_id"]
        self.worksheet_index = google_sheets_config["worksheet_index"]
        self.column_index = google_sheets_config["column_index"]

        self.json_manager = JSONManager(json_paths["selected_data"])

        self.creds = Credentials.from_service_account_file(
            self.creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        self.client = gspread.authorize(self.creds)
        self.sheet = self.client.open_by_key(self.sheet_id).get_worksheet(self.worksheet_index)

    def append_to_cell(self):
        """Добавляет текст в ячейку столбца 13 на строке, указанной в JSON."""
        json_data = self.json_manager.load_json()
        if isinstance(json_data, list):
            for item in json_data:
                self._process_item(item)
        else:
            print("❌ Ошибка: json_data должен быть списком словарей.")

    def _process_item(self, item):
        """Обрабатывает один элемент JSON (словарь)."""
        try:
            row_index = item.get("index")
            if not row_index:
                print("❌ Ошибка: индекс строки не найден в JSON.")
                return

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_text = f"{current_time}, едет, {item.get('гео', '')}, {item.get('коор', '')}"
            cell_value = self.sheet.cell(row_index, 13).value
            updated_value = f"{cell_value}\n{new_text}" if cell_value else new_text

            self.sheet.update_cell(row_index, 13, updated_value)
            print(f"✅ Данные успешно добавлены в строку {row_index}, колонку 13.")
        except Exception as e:
            print(f"❌ Ошибка при добавлении данных: {e}")

    def load_data(self):
        return self.sheet.get_all_values()

    def refresh_name(self):
        """Обновляет JSON без удаления существующих записей."""
        rows = self.load_data()
        existing_data = self.json_manager.load_json()
        existing_indexes = {entry["index"] for entry in existing_data}
        new_entries = []

        for i, row in enumerate(rows[2:], start=3):
            if len(row) < self.column_index or row[self.column_index - 1].strip() != "Готов":
                row[3] = re.sub(r'\s+', '', row[3])[:6] + ' ' + re.sub(r'\s+', '', row[3])[6:9]
                if i not in existing_indexes:
                    new_entries.append({
                        "index": i,
                        "ТС": row[3],
                        "ФИО": row[5],
                        "Погрузка": row[7],
                        "Выгрузка": row[8],
                    })

        self.json_manager.update_json(new_entries)
        print(f"Обновлено: добавлено {len(new_entries)} новых записей.")
