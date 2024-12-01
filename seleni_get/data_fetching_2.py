from google.oauth2.service_account import Credentials
import gspread
import json
import re

# Конфигурация
CREDS_FILE = "config/Credentials_wialon.json"
SHEET_ID = "1Yv4RJ0O4icSr_J2DQOwPG7V8JW7Pj_LR5egerdiKSOY"
WORKSHEET_INDEX = 3
COLUMN_INDEX = 14  # Номер колонки (начиная с 1)


# Установление соединения с Google Sheets
def get_spreadsheet_data():
    """Получает данные из Google Sheets."""
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).get_worksheet(WORKSHEET_INDEX)
    return sheet.get_all_values()


# Проверка и изменение структуры данных
def cleanup_json_data(input_file: str, output_file: str):
    """Очищает и обновляет JSON-файл, удаляя первое слово в строках с 3 словами."""
    try:
        with open(input_file, "r", encoding="utf-8") as file:
            data = json.load(file)

        for item in data["items"]:
            name = item.get("Наименование", "")
            words = name.split()
            if len(words) == 3:
                # Удаляем первое слово и пробел после него
                item["Наименование"] = " ".join(words[1:])

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка при работе с JSON-файлом: {e}")


# Обновление данных из Google Sheets
def refresh_sheet_data(rows, output_file: str):
    """  Обрабатывает данные из Google Sheets и сохраняет их в JSON-файл."""
    selected_data = []

    for i, row in enumerate(rows[2:], start=3):  # Пропускаем заголовки (строки 0-1)
        # Проверяем значение в нужной колонке
        if len(row) < COLUMN_INDEX or row[COLUMN_INDEX - 1].strip() != "Готово":
            # Оригинальная обработка номера ТС
            row[3] = (re.sub(r"\s+", "", row[3])[:6] + " " + re.sub(r"\s+", "", row[3])[6:9])

            ts_data = {
                "index": i,
                "ТС": row[3],
                "ФИО": row[5].strip(),
                "Погрузка": row[7].strip(),
                "Выгрузка": row[8].strip(),
            }

            selected_data.append(ts_data)
    print(selected_data)
    # Сохранение результата в JSON
    try:
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(selected_data, file, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"Ошибка записи в файл: {e}")


# Основная функция
def main():
    """Основная логика программы."""
    # Получение данных из Google Sheets
    rows = get_spreadsheet_data()

    # Обновление данных из таблицы
    refresh_sheet_data(rows, "Dear PyGui/selected_data.json")

    # Очистка JSON-файла
    # cleanup_json_data("selected_data.json", "cleaned_data.json")

