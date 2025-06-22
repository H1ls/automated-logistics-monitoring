
from Navigation_Bot.googleSheetsManager import GoogleSheetsManager
test_item = {
    "index": 2601,
    "гео": "Тест: Санкт-Петербург, Невский проспект, 1",
    "коор": "59.9386, 30.3141",
    "скорость": 0,
    "ТС": "ТЕСТ 001"
}

gs = GoogleSheetsManager(log_func=print)
gs._append_entry(test_item, column=12)  # колонка = индекс столбца, откуда начинается выгрузка
