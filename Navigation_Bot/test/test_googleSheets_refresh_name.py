from Navigation_Bot.requirements import *


class GoogleSheetsManager:
    def __init__(self, creds_file, sheet_id, worksheet_index, column_index):
        self.creds_file = creds_file
        self.sheet_id = sheet_id
        self.worksheet_index = worksheet_index
        self.column_index = column_index
        self.file_path = '../config/selected_data.json'
        self.creds = Credentials.from_service_account_file(
            self.creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        self.client = gspread.authorize(self.creds)
        self.sheet = self.client.open_by_key(self.sheet_id).get_worksheet(self.worksheet_index)

    def _load_existing_data(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def refresh_name(self, file_path):
        try:
            rows = self.sheet.get_all_values()
            existing_data = self._load_existing_data(file_path)
            existing_indexes = {entry["index"] for entry in existing_data}
            new_entries = []

            for i, row in enumerate(rows[2:], start=3):
                if len(row) < self.column_index:
                    continue

                status = row[self.column_index - 1].strip()
                if status == "Готов":
                    continue

                if i in existing_indexes:
                    continue

                if len(row) < 9:
                    continue

                ts = row[3].replace(" ", "")[:6] + ' ' + row[3].replace(" ", "")[6:9]

                new_entries.append({
                    "index": i,
                    "ТС": ts,
                    "ФИО": row[5],
                    "Погрузка": row[7],
                    "Выгрузка": row[8],
                })

            updated_data = existing_data + new_entries
            self.save_json(updated_data, file_path)
            print(f"[INFO] Обновлено: добавлено {len(new_entries)} новых записей.")
        except Exception as e:
            print(f"[ERROR] refresh_name: {e}")

    def clean_ready_entries(self, file_path):
        try:
            data = self._load_existing_data(file_path)
            statuses = self.sheet.col_values(self.column_index)
            cleaned_data = []

            for entry in data:
                idx = entry.get("index")
                if not idx or idx > len(statuses):
                    continue
                status = statuses[idx - 1].strip()
                if status != "Готов":
                    cleaned_data.append(entry)
                else:
                    print(f"[INFO] Удалено: index {idx}, ТС: {entry.get('ТС')}")

            self.save_json(cleaned_data, file_path)
            print(f"[INFO] Очищено. Осталось записей: {len(cleaned_data)}")
        except Exception as e:
            print(f"[ERROR] clean_ready_entries: {e}")

    def sync_with_sheet(self, file_path):
        print("[SYNC] Начало синхронизации с Google Sheet...")
        self.clean_ready_entries(file_path)
        self.refresh_name(file_path)
        print("[SYNC] Синхронизация завершена.\n")

    def save_json(self, data: Any, file_path: str) -> None:
        try:
            with open(file_path, "w", encoding="utf-8") as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка при сохранении данных в файл: {e}")


sheets_manager = GoogleSheetsManager(
    creds_file="../config/Credentials_wialon.json",
    sheet_id="1uz2ZXlCBltsD8s96GNuQELDEJ5_qCBuDFP2dvxeNqsU",
    worksheet_index=3,
    column_index=14)

path = '../config/selected_data.json'

sheets_manager.sync_with_sheet(path)
