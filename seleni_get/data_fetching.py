# Получение данных из Excel через API.
"""
    Функция получает данные из электронной таблицы Google, обрабатывает их и сохраняет выбранные данные в JSON-файл.
    Она открывает рабочий лист, перебирает его строки, выбирает и обрабатывает данные на основе условий и сохраняет их в файл JSON.
    Функция ищет строки, где значение в определенном столбце (задается индексом_столбца) не «Готов»,извлекает и форматирует 
    соответствующую информацию.
    Side effects:
    – Считывает данные из электронной таблицы Google, используя предопределенные учетные данные и информацию о листе.
    – Записывает обработанные данные в файл с именем 'selected_data.json' в текущем каталоге.

    Примечание:
       – Функция использует глобальные переменные (client, sheet_id, worksheet_index, column_index),
         которые должны быть правильно установлены перед вызовом.
"""
from google.oauth2.service_account import Credentials
import gspread
import json
import re

# Конфигурация
CREDS_FILE = "config/Credentials_wialon.json"
SHEET_ID = "1Yv4RJ0O4icSr_J2DQOwPG7V8JW7Pj_LR5egerdiKSOY"
WORKSHEET_INDEX = 3  # Лист с обычными задачами
COLUMN_INDEX = 14  # Колонка = "Готово", Номер колонки (начиная с 1)
creds = Credentials.from_service_account_file(CREDS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])


def get_spreadsheet():
    """Получает данные из Google Sheets."""
    # Настройка доступа к Google Sheets
    client = gspread.authorize(creds)
    # Открываем Google Sheets по ID и выбираем лист
    sheet = client.open_by_key(SHEET_ID).get_worksheet(WORKSHEET_INDEX)
    # Получаем все строки из листа
    rows = sheet.get_all_values()
    return rows


def check_up_id_car():
    """Очищает и обновляет JSON-файл, удаляя первое слово в строках с 3 словами."""
    # ПОВТОР, вынести в отдельную функцию
    with open("Dear PyGui/selected_data.json", "r", encoding="utf-8") as file:
        data = json.load(file)
    for item in data["items"]:
        name = item["Наименование"]
        # Разделяем строку на слова
        words = name.split()
        # Проверяем, если слов ровно 3
        if len(words) == 3:
            # Удаляем первое слово и пробел после него
            item["Наименование"] = ' '.join(words[1:])
    # ПОВТОР, вынести в отдельную функцию
    with open("Dear PyGui/selected_data.json", "w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=4)


def refresh_name(rows):
    """  Обрабатывает данные из Google Sheets и сохраняет их в JSON-файл."""
    selected_data = []
    # Проходим по каждой строке, начиная с первой после заголовка
    # enumerate с start=3, учитывать заголовок
    for i, row in enumerate(rows[2:], start=3):
        # Проверяем значение в нужной колонке
        if len(row) < COLUMN_INDEX or row[COLUMN_INDEX - 1].strip() != "Готов":
            # Номер ТС: Е 153 УА 790  969-018-95-40 -> Е 153 УА 790
            row[3] = re.sub(r'\s+', '', row[3])[:6] + ' ' + re.sub(r'\s+', '', row[3])[6:9]
            # Добавление данных в список для записи в JSON
            selected_data.append({
                "index": i,
                "ТС": row[3],  # row[3] = ТС
                "ФИО": row[5],  # row[5] = ФИО
                "Погрузка": row[7],  # row[7],=Погрузка
                "Выгрузка": row[8],  # row[8] = выгрузка
            })
    # ПОВТОР, вынести в отдельную функцию
    # Записываем полученные данные в JSON-файл
    with open("Dear PyGui/selected_data.json", "w", encoding="utf-8") as json_file:
        json.dump(selected_data, json_file, ensure_ascii=False, indent=4)
