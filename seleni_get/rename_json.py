from datetime import datetime, timedelta
import json
import os


def check_up_id_car():
    """Исправляем номер машины(Наименование), для дальнейше работы с навигацией"""
    with open("Id_car.json", "r", encoding="utf-8") as file:
        data = json.load(file)
    # for item in data["Лист1"]:
    for item in data:
        if "Наименование" in item and isinstance(item["Наименование"], str):
            name = item["Наименование"]
            words = name.split()  # Разделяем строку на слова
            if len(words) == 3:  # Проверяем, если слов ровно 3
                item["Наименование"] = ' '.join(words[1:])  # Удаляем первое слово и пробел после него

    with open("Id_car.json", "w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=4)


def get_id_for_data():
    """Добавляет поле "id" к каждому элементу JSON файла, где есть поле "ТС" и "Наименование"""
    with open("selected_data.json", "r", encoding="utf-8") as file1:
        json1 = json.load(file1)
    # Загружаем второй JSON файл, где содержатся ИДОбъекта
    with open("Id_car.json", "r", encoding="utf-8") as file2:
        json2 = json.load(file2)

    # Создаем словарь для быстрого доступа к данным json2 по "Наименование"
    lookup = {entry["Наименование"]: entry["ИДОбъекта в центре мониторинга"] for entry in json2}

    # Проходим по каждому элементу json1 и добавляем "ИДОбъекта", если находим совпадение
    for item in json1:
        if item["ТС"] in lookup:
            item["id"] = lookup[item["ТС"]]
    with open("selected_data.json", "w", encoding="utf-8") as file:
        json.dump(json1, file, ensure_ascii=False, indent=4)


def normalization_json():
    # Путь к файлу JSON
    file_path = "Id_car.json"

    # Время последнего изменения файла
    last_modified_time = os.path.getmtime(file_path)
    last_modified_datetime = datetime.fromtimestamp(last_modified_time)

    # Проверка: прошло ли больше 12 часов с момента изменения
    if datetime.now() - last_modified_datetime < timedelta(hours=12):
        print("Файл не изменялся за последние 12 часов. Никаких действий не требуется.")
    else:
        print("Файл был изменён за последние 12 часов. Вносим изменения...")

        # Чтение содержимого JSON
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Обработка каждого объекта в списке "Лист1"
        for item in data["Лист1"]:
            name = item.get("Наименование", "")

            # Удаляем первое слово до пробела
            if " " in name:
                name = name.split(" ", 1)[1]  # Удаляем первое слово
                # Убираем все оставшиеся пробелы
                name = name.replace(" ", "")
                item["Наименование"] = name

        # Сохранение изменений обратно в файл
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

        print("Изменения успешно сохранены.")
