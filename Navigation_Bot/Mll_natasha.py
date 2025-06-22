import re
from datetime import datetime


class MllParser:
    def __init__(self, default_year=2025):
        self.default_year = default_year
        self.date_pattern = r"\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b"
        self.time_pattern = r"\b\d{1,2}[:\-]\d{2}(?::\d{2})?\b"
        self.coord_pattern = r"\b\d{2}\.\d{5,},\s*\d{2,3}\.\d{5,}\b"
        self.address_keywords = [
            "обл", "г.", "ул", "д.", "пер", "пр-д", "р-н", "просп", "пл", "квартал", "тер", "промзона", "село", "п.", "поселок"
        ]

    def clean(self, text):
        return re.sub(r'\s+', ' ', text).strip()

    def extract(self, text: str, prefix: str = "Точка") -> list[dict]:
        result = {}
        raw = text.replace("\n", " ").replace("—", "-")

        # 🔹 Дата
        dates = re.findall(self.date_pattern, raw)
        date_str = "Не указано"
        if dates:
            parts = dates[0].split(".")
            if len(parts) == 3:
                date_str = f"{int(parts[0]):02d}.{int(parts[1]):02d}.{int(parts[2])}"
            elif len(parts) == 2:
                date_str = f"{int(parts[0]):02d}.{int(parts[1]):02d}.{self.default_year}"
        result["Дата 1"] = date_str

        # 🔹 Время
        times = re.findall(self.time_pattern, raw)
        result["Время 1"] = times[0] if times else "Не указано"

        # 🔹 Координаты
        coords = re.findall(self.coord_pattern, raw)
        coord_text = coords[0] if coords else None

        # 🔹 Адрес
        address = "Не указано"
        candidates = re.split(r"[.!?]", raw)
        for line in candidates:
            if any(kw in line.lower() for kw in self.address_keywords):
                address = self.clean(line)
                break

        result[f"{prefix} 1"] = address

        # 🔹 Остальное — без уже извлечённого
        used_parts = dates + times + (coords if coords else []) + ([address] if address != "Не указано" else [])
        leftover = raw
        for item in used_parts:
            leftover = leftover.replace(item, " ")
        result["Другое"] = self.clean(leftover)

        # 🔹 Координаты — если адрес найден, то в "Другое"
        if coord_text and address != f"Координаты: {coord_text}" and address != "Не указано":
            result["Другое"] += f" Координаты: {coord_text}"

        return [result]

text = """02.02.2025, прибыть до 16:00:00, ООО "Торговый дом "Эковер"
Свердловская обл., г. Асбест, 101 квартал, 57.006083, 61.547357"""

parser = MllParser()
parsed = parser.extract(text, prefix="Выгрузка")

for row in parsed:
    for k, v in row.items():
        print(f"{k}: {v}")
    print("---")
