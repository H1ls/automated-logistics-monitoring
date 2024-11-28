import json
import re

# Паттерны для обрезки ненужной информации
end_patterns = [
    r"тел\s*\d[\d\s\-]{8,}",
    r"Контакт:?\s*\d[\d\s\-]{8,}",
    r"\sГП\s",
    r"\sООО\s",
    r"\(Согласт\s",
    r"ТТН\s",
    r"\ГО\s",
    r"\тел\s",
    r"\ООО\s",
    r"\Контрагент\s",
    r"\по ТТН\s",
    r"контакт\s*\d{1,2}:\d{2}",
]


def parse_info(text, end_patterns, address="Точка"):
    """Вырезания даты/времени/адреса из полученных данных с таблицы Goggle"""
    # Новый паттерн для поиска точек выгрузки
    unload_pattern = re.compile(
        r"(\d+\))?\s*(\d{1,2}\.\d{2}\.\d{4})\s*,?\s*(\d{1,2}[:\-]\d{2}(?::\d{2})?)?\s*,?\s*(.*?)(?=\d+\)|$)",
        re.DOTALL, )
    # Поиска времени в тексте
    time_pattern = re.compile(r"\b(\d{1,2}[:\-]\d{2}(?::\d{2})?)\b")
    # Для погрузок или выгрузок
    results = []
    # Поиск всех погрузок/выгрузок в тексте
    for i, match in enumerate(unload_pattern.finditer(text), 1):
        date = match.group(2)
        time = match.group(3) or "Не указано"
        address_info = match.group(4).strip()
        # "прибыть к|до" + , и space
        address_info = re.sub(r"\bприбыть\s+(к|до)\b\s*,?\s*", "", address_info)
        # Ищем время в любой части адреса, если не было найдено в основном паттерне
        if time == "Не указано":
            time_match = time_pattern.search(address_info)
            if time_match:
                time = time_match.group(1)
                # Удаляем найденное время из адреса
                address_info = address_info.replace(time_match.group(0), "").strip()
        # Убираем запятую, если она осталась перед адресом
        address_info = re.sub(r"^,\s*", "", address_info)
        # Применяем фильтры к адресу, чтобы обрезать его на найденном паттерне
        for pattern in end_patterns:
            end_match = re.search(pattern, address_info)
            if end_match:
                address_info = address_info[: end_match.start()].strip()
                break
        results.append(
            {f"{address} "
             f"{i}": address_info,
             f"Дата {i}": date,
             f"Время {i}": time
             })
    return results


def start_clean():
    """Cчитывает данные из «selected_data.json», обрабатывает «Погрузка» и «Выгрузка»"""
    with open("selected_data.json", "r", encoding="utf-8") as file:
        data = json.load(file)
    for item in data:
        # Обрабатываем поле "Погрузка/Выгрузка" и сохраняем как массив
        if "Погрузка" in item and isinstance(item["Погрузка"], str):
            item["Погрузка"] = parse_info(item["Погрузка"], end_patterns)
        if "Выгрузка" in item and isinstance(item["Выгрузка"], str):
            item["Выгрузка"] = parse_info(item["Выгрузка"], end_patterns)
    with open("selected_data.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
