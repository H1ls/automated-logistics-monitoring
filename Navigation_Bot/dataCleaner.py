import json
import logging
import os
import re

from Navigation_Bot.jSONManager import JSONManager

"""2. Очистка данных"""


class DataCleaner:
    def __init__(self,jsons,input_filepath, id_filepath,log_func=None):
        self.json_manager = jsons
        self.selected_data_path = input_filepath
        self.id_car_path = id_filepath
        self.log = log_func or print

        self.end_patterns = [
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
            r'по ттн'
        ]


    def _file_exists(self, filepath):
        if not os.path.exists(filepath):
            self.log(f"Файл {filepath} не найден.")
            return False
        return True

    def _parse_info(self, text, address="Точка"):
        unload_pattern = re.compile(
            r"(\d+\))?\s*(\d{1,2}\.\d{2}\.\d{4})\s*,?\s*(\d{1,2}[:\-]\d{2}(?::\d{2})?)?\s*,?\s*(.*?)(?=\d+\)|$)",
            re.DOTALL
        )
        time_pattern = re.compile(r"\b(\d{1,2}[:\-]\d{2}(?::\d{2})?)\b")
        results = []

        for i, match in enumerate(unload_pattern.finditer(text), 1):
            date = match.group(2)
            time = match.group(3) or "Не указано"
            address_info = match.group(4).strip()

            address_info = re.sub(r"\bприбыть\s+(к|до)\b\s*,?\s*", "", address_info)

            if time == "Не указано":
                time_match = time_pattern.search(address_info)
                if time_match:
                    time = time_match.group(1)
                    address_info = address_info.replace(time_match.group(0), "").strip()

            address_info = re.sub(r"^,\s*", "", address_info)

            for pattern in self.end_patterns:
                end_match = re.search(pattern, address_info)
                if end_match:
                    address_info = address_info[: end_match.start()].strip()
                    break

            results.append({
                f"{address} {i}": address_info,
                f"Дата {i}": date,
                f"Время {i}": time
            })
        self.log("Очистка загруженных адресов")
        return results

    def start_clean(self):
        if not self._file_exists(self.selected_data_path):
            return

        with open(self.selected_data_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        for item in data:
            if isinstance(item.get("Погрузка"), str):
                item["Погрузка"] = self._parse_info(item["Погрузка"], "Погрузка")
            if isinstance(item.get("Выгрузка"), str):
                item["Выгрузка"] = self._parse_info(item["Выгрузка"], "Выгрузка")

            # Проверка на пустые значения в Погрузка/Выгрузка
            if not item.get("Погрузка") or not item.get("Выгрузка"):
                self.log(f"Пропущена запись {item.get('ТС')} из-за пустых данных.")
                continue

        self.json_manager.save_json(data, self.selected_data_path)
        self.log(f" Данные очищены и сохранены в {self.selected_data_path}.")

    def clean_vehicle_names(self):
        if not os.path.exists(self.id_car_path):
            return

        with open(self.id_car_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        for item in data:
            if "Наименование" in item and isinstance(item["Наименование"], str):
                words = item["Наименование"].split()
                if len(words) == 3:
                    item["Наименование"] = ' '.join(words[1:])
        self.json_manager.save_json(data, self.id_car_path)
        self.log(f" Данные по наименованиям машин очищены и сохранены в {self.id_car_path}.")


    def add_id_to_data(self):
        if not (self._file_exists(self.selected_data_path) and self._file_exists(self.id_car_path)):
            return

        with open(self.selected_data_path, "r", encoding="utf-8") as file1:
            json1 = json.load(file1)
        with open(self.id_car_path, "r", encoding="utf-8") as file2:
            json2 = json.load(file2)

        # Создаём словарь для поиска: Наименование -> ID
        lookup = {
            entry["Наименование"]: entry["ИДОбъекта в центре мониторинга"]
            for entry in json2
            if "Наименование" in entry and "ИДОбъекта в центре мониторинга" in entry
        }

        for item in json1:
            original_ts = item.get("ТС", "").strip()

            # Убираем пробелы и добавляем один перед регионом
            raw = re.sub(r"\s+", "", original_ts)
            if len(raw) >= 9:
                normalized = raw[:6] + ' ' + raw[6:9]
            else:
                normalized = raw  # если что-то пошло не так

            if normalized in lookup:
                item["ТС"] = normalized  # заменим ТС на нормализованный
                item["id"] = lookup[normalized]

        self.json_manager.save_json(json1, self.selected_data_path)
        self.log(f" Присвоение id в json завершено.")
