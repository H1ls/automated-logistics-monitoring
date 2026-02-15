import re
import os
from pathlib import Path
from typing import List, Dict, Any

from Navigation_Bot.core.paths import INPUT_FILEPATH, ID_FILEPATH
from Navigation_Bot.core.dataContext import DataContext

"""2. Очистка данных"""


class DataCleaner:
    def __init__(self, data_context: DataContext | None = None,
                 id_context: DataContext | None = None,
                 log_func=print):

        self.log = log_func

        self.data_context = data_context or DataContext(str(INPUT_FILEPATH), log_func=log_func)
        self.id_context = id_context or DataContext(str(ID_FILEPATH), log_func=log_func)

        self.json_data: List[Dict[str, Any]] = self.data_context.get() or []
        self.id_data: List[Dict[str, Any]] = self.id_context.get() or []

        self.unload_re = re.compile(
            r"(\d+\))?\s*"
            r"(\d{1,2}\.\d{2}\.\d{4})\s*,?\s*"  # дата
            r"(\d{1,2}[:\-]\d{2}(?::\d{2})?)?\s*,?\s*"  # время (опц.)
            r"(.*?)(?=\d+\)|$)",  # адрес до следующего блока или конца
            re.DOTALL
        )
        self.time_re = re.compile(r"\b(\d{1,2}[:\-]\d{2}(?::\d{2})?)\b")

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
            r"\bпо\s+ттн\b",
        ]

    def _file_exists(self, filepath):
        if not os.path.exists(filepath):
            self.log(f"Файл {filepath} не найден.")
            return False
        return True

    def _parse_info(self, text: str, prefix: str) -> list[dict]:

        if not isinstance(text, str) or not text.strip():
            return []

        results: list[dict] = []
        consumed: list[tuple[int, int]] = []

        for i, m in enumerate(self.unload_re.finditer(text), 1):
            date = (m.group(2) or "").strip()
            time = (m.group(3) or "").strip() or "Не указано"
            addr = (m.group(4) or "").strip()

            # убираем "прибыть к/до"
            addr = re.sub(r"\bприбыть\s+(к|до)\b\s*,?\s*", "", addr, flags=re.IGNORECASE)

            # если время оказалось внутри адреса
            if time == "Не указано":
                t = self.time_re.search(addr)
                if t:
                    time = t.group(1)
                    addr = addr.replace(t.group(0), "").strip()

            # подчистим запятую в начале
            addr = re.sub(r"^,\s*", "", addr)

            # отрезаем хвосты по стоп-словам
            for p in self.end_patterns:
                end = re.search(p, addr, flags=re.IGNORECASE)
                if end:
                    addr = addr[: end.start()].strip()
                    break

            results.append({
                f"{prefix} {i}": addr,
                f"Дата {i}": date,
                f"Время {i}": time
            })
            consumed.append(m.span())

        # другое/комментарий - всё, что не попало в матчи
        other_parts: list[str] = []
        last = 0
        for s, e in consumed:
            if s > last:
                other_parts.append(text[last:s].strip())
            last = e
        if last < len(text):
            other_parts.append(text[last:].strip())

        # Соберём комментарий
        comment = "\n".join(p for p in other_parts if p)
        if comment:
            results.append({"Комментарий": comment})

        return results

    def start_clean(self, only_indexes: set[int] | None = None) -> None:
        """
        1) Один раз сохраняем сырые строки в raw_load / raw_unload (для ML)
        2) Преобразуем строки Погрузка/Выгрузка → список блоков
        3) Чистим поле 'ТС'
        4) Привязываем ID из Id_car.json
        5) Сохраняем через DataContext
        """
        if not Path(self.data_context.filepath).exists():
            self.log(f"❌ Файл не найден: {self.data_context.filepath}")
            return

        # актуальные данные и id-справочник
        self.json_data = self.data_context.get() or []
        self.id_data = self.id_context.get() or []

        for item in self.json_data:
            if only_indexes is not None and item.get("index") not in only_indexes:
                continue
            #  RAW для ML
            if isinstance(item.get("Погрузка"), str) and not item.get("raw_load"):
                item["raw_load"] = item["Погрузка"]

            if isinstance(item.get("Выгрузка"), str) and not item.get("raw_unload"):
                item["raw_unload"] = item["Выгрузка"]

            #  Парсинг в структурированный вид
            if isinstance(item.get("Погрузка"), str):
                item["Погрузка"] = self._parse_info(item["Погрузка"], "Погрузка")

            if isinstance(item.get("Выгрузка"), str):
                item["Выгрузка"] = self._parse_info(item["Выгрузка"], "Выгрузка")

            if not item.get("Погрузка") or not item.get("Выгрузка"):
                self.log(f"⚠️ Пропущена запись {item.get('ТС')} — пустая Погрузка или Выгрузка.")

        self._clean_vehicle_names()
        self._add_id_to_data()

        self.data_context.set(self.json_data)

    def _clean_vehicle_names(self) -> None:
        """Оставляем в 'ТС' только номер (без телефона и переносов)."""
        for row in self.json_data:
            ts = row.get("ТС", "")
            if isinstance(ts, str) and "\n" in ts:
                row["ТС"] = ts.split("\n", 1)[0].strip()

    def _add_id_to_data(self) -> None:
        """
        Привязка ID к ТС:
          - ключ по справочнику: 'Наименование' без пробелов
          - ключ по данным: 'ТС' без пробелов (и без телефона)
        """
        # создаём lookup: "Р703ТХ790" → 123456
        lookup = {}
        for entry in (self.id_data or []):
            name = entry.get("Наименование")
            obj_id = entry.get("ИДОбъекта в центре мониторинга")
            if isinstance(name, str) and obj_id is not None:
                key = re.sub(r"\s+", "", name)
                lookup[key] = obj_id

        for row in self.json_data:
            ts = row.get("ТС", "")
            if not isinstance(ts, str) or not ts:
                continue
            ts_clean = ts.split("\n", 1)[0].strip()
            key = re.sub(r"\s+", "", ts_clean)
            found = lookup.get(key)
            if found is not None:
                row["id"] = found
            else:
                self.log(f"❌ Не найден ID для ТС: {ts_clean}")
