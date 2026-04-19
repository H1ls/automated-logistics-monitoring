from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class TaskEditService:
    log: Callable[[str], None] | None = None

    def build_load_patch(self, data_block: list, meta: dict | None = None) -> tuple[bool, dict | None, str | None]:
        if not data_block:
            return False, None, "empty_load_block"

        meta = meta or {}
        patch = {"Погрузка": data_block}

        if meta.get("Время отправки"):
            patch["Время отправки"] = meta["Время отправки"]
        if meta.get("Транзит"):
            patch["Транзит"] = meta["Транзит"]

        return True, patch, None

    def build_unload_patch(self, data_block: list, meta: dict | None = None) -> tuple[bool, dict | None, str | None]:
        if not data_block:
            return False, None, "empty_unload_block"

        return True, {"Выгрузка": data_block}, None

    def build_task_from_buffer(self, ts_phone: str, ka: str, fio: str, buffer: dict, ) -> tuple[
        bool, dict | None, str | None]:
        ts_phone = (ts_phone or "").strip()
        ka = (ka or "").strip()
        fio = (fio or "").strip()
        buffer = buffer or {}

        if not ts_phone:
            return False, None, "missing_ts"
        if not ka:
            return False, None, "missing_ka"
        if not fio:
            return False, None, "missing_fio"
        if "Погрузка" not in buffer or not buffer["Погрузка"]:
            return False, None, "missing_load"
        if "Выгрузка" not in buffer or not buffer["Выгрузка"]:
            return False, None, "missing_unload"

        parts = ts_phone.split()
        ts = " ".join(parts[:-1]) if len(parts) > 1 else ts_phone
        phone = parts[-1] if len(parts) > 1 else ""

        task = {"ТС": ts,
                "Телефон": phone,
                "ФИО": fio,
                "КА": ka,
                "Погрузка": buffer.get("Погрузка", []),
                "Выгрузка": buffer.get("Выгрузка", []),}

        if "Время отправки" in buffer:
            task["Время отправки"] = buffer["Время отправки"]
        if "Транзит" in buffer:
            task["Транзит"] = buffer["Транзит"]

        return True, task, None
