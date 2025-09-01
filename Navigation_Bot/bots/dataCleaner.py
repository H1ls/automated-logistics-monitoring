import os
import re
from pathlib import Path
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import INPUT_FILEPATH, ID_FILEPATH

"""2. Очистка данных"""

"""TO DO 1._parse_info() - разбить 
         2.Объединение с ML"""


class DataCleaner:
    def __init__(self, json_manager=None, selected_data_path=None, id_path=None, log_func=print):
        self.json_manager = json_manager or JSONManager()
        self.log = log_func
        self.selected_data_path = Path(selected_data_path or INPUT_FILEPATH)
        self.id_path = Path(id_path or ID_FILEPATH)
        self.json_data = self.json_manager.load_json(str(self.selected_data_path))
        self.id_data = self.json_manager.load_json(str(self.id_path))

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

        return results

    def start_clean(self):
        if not self.selected_data_path.exists():
            self.log(f"❌ Файл не найден: {self.selected_data_path}")
            return

        self.json_data = self.json_manager.load_json(str(self.selected_data_path))

        for item in self.json_data:
            if isinstance(item.get("Погрузка"), str):
                item["Погрузка"] = self._parse_info(item["Погрузка"], "Погрузка")

            if isinstance(item.get("Выгрузка"), str):
                item["Выгрузка"] = self._parse_info(item["Выгрузка"], "Выгрузка")

            if not item.get("Погрузка") or not item.get("Выгрузка"):
                self.log(f"⚠️ Пропущена запись {item.get('ТС')} — пустая Погрузка или Выгрузка.")

        self._clean_vehicle_names()
        self._add_id_to_data()

        self.json_manager.save_in_json(self.json_data, self.selected_data_path)
        # self.log(f"✅ Данные очищены и сохранены: {self.selected_data_path}")

    def _clean_vehicle_names(self):
        for row in self.json_data:
            ts = row.get("ТС", "")
            if ts and "\n" in ts:
                row["ТС"] = ts.split("\n")[0].strip()

    def _add_id_to_data(self):
        # Создаём словарь: "Р703ТХ790" → ID
        lookup = {
            re.sub(r"\s+", "", entry["Наименование"]): entry["ИДОбъекта в центре мониторинга"]
            for entry in self.id_data if "Наименование" in entry
        }

        for row in self.json_data:
            ts = row.get("ТС", "")
            ts_clean = ts.split("\n")[0].strip()  # убираем телефон, если есть
            ts_key = re.sub(r"\s+", "", ts_clean)  # убираем все пробелы для сравнения

            found_id = lookup.get(ts_key)
            if found_id:
                row["id"] = found_id
                # self.log(f"✔️ Привязан ID {found_id} к ТС: {ts_clean}")
            else:
                self.log(f"❌ Не найден ID для ТС: {ts_clean}")
