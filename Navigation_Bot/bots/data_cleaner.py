import re
from typing import Any

from Navigation_Bot.core.repositories.vehicle_registry_fields import compact_vehicle_key
from Navigation_Bot.bots.route_info_parser import RouteInfoParser
from Navigation_Bot.core.logging import normalize_log_func

"""2. Очистка данных"""


class DataCleaner:
    def __init__(self, task_repository=None,
                 id_context=None,
                 log_func=print):

        self.log = normalize_log_func(log_func)

        if task_repository is None:
            raise RuntimeError("DataCleaner requires task_repository")
        if id_context is None:
            raise RuntimeError("DataCleaner requires vehicle repository")

        self.task_repository = task_repository
        self.vehicle_repository = id_context
        self.route_parser = RouteInfoParser()

        self.task_rows: list[dict[str, Any]] = self.task_repository.get() or []
        self.vehicle_lookup: dict[str, dict] = self.vehicle_repository.registry_lookup()

    def _parse_info(self, text: str, prefix: str) -> list[dict]:
        return self.route_parser.parse(text, prefix)

    def _clean_address(self, addr: str) -> str:
        return self.route_parser.clean_address(addr)

    def start_clean(self, only_indexes: set[int] | None = None) -> None:
        """
        1) Один раз сохраняем сырые строки в raw_load / raw_unload (для ML)
        2) Преобразуем строки Погрузка/Выгрузка в список блоков
        3) Чистим поле 'ТС'
        4) Привязываем Wialon ID из таблицы vehicles
        5) Сохраняем через TaskRepository
        """
        self.task_rows = self.task_repository.get() or []
        self.vehicle_lookup = self.vehicle_repository.registry_lookup()

        for item in self.task_rows:
            if only_indexes is not None and item.get("index") not in only_indexes:
                continue

            if isinstance(item.get("Погрузка"), str) and not item.get("raw_load"):
                item["raw_load"] = item["Погрузка"]

            if isinstance(item.get("Выгрузка"), str) and not item.get("raw_unload"):
                item["raw_unload"] = item["Выгрузка"]

            if isinstance(item.get("Погрузка"), str):
                item["Погрузка"] = self.route_parser.parse(item["Погрузка"], "Погрузка")

            if isinstance(item.get("Выгрузка"), str):
                item["Выгрузка"] = self.route_parser.parse(item["Выгрузка"], "Выгрузка")

            if not item.get("Погрузка") or not item.get("Выгрузка"):
                self.log(f"⚠️ Пропущена запись {item.get('ТС')} — пустая Погрузка или Выгрузка.")

        self._clean_vehicle_names()
        self._add_id_to_data()

        self.task_repository.set(self.task_rows, source="cleaner")

    def _clean_vehicle_names(self) -> None:
        """Оставляем в 'ТС' только номер (без телефона и переносов)."""
        for row in self.task_rows:
            ts = row.get("ТС", "")
            if isinstance(ts, str) and "\n" in ts:
                row["ТС"] = ts.split("\n", 1)[0].strip()

    def _add_id_to_data(self) -> None:
        """
        Привязка ID к ТС:
          - ключ по справочнику vehicles: monitoring_name/plate_number без пробелов
          - ключ по данным: 'ТС' без пробелов (и без телефона)
        """
        for row in self.task_rows:
            ts = row.get("ТС", "")
            if not isinstance(ts, str) or not ts:
                continue
            ts_clean = ts.split("\n", 1)[0].strip()
            key = compact_vehicle_key(ts_clean)
            found = self._find_vehicle_by_key(key)
            if found is not None:
                row["id"] = found["monitoring_id"]
                if found.get("plate_number"):
                    row["ТС"] = found["plate_number"]
            else:
                self.log(f"❌ Не найден ID для ТС: {ts_clean}")

    def _find_vehicle_by_key(self, key: str) -> dict | None:
        found = self.vehicle_lookup.get(key)
        if found is not None:
            return found

        # Если телефон был склеен с ТС, регион вида 750 может быть разобран как 75.
        # В справочнике такие машины хранятся с полным трехзначным регионом.
        if re.match(r"^[А-ЯЁA-Z]\d{3}[А-ЯЁA-Z]{2}\d{2}$", key):
            return self.vehicle_lookup.get(f"{key}0")

        return None
