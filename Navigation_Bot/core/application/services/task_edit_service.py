from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class TaskEditService:
    log: Callable[[str], None] | None = None

    def build_load_patch(self, data_block: list, meta: dict | None = None) -> tuple[bool, dict | None, str | None]:
        if not data_block:
            return False, None, "empty_load_block"

        meta = meta or {}
        patch = {
            "loads": self._legacy_blocks_to_points(data_block, "Погрузка"),
            "Погрузка": data_block,
        }

        if meta.get("Время отправки"):
            patch["Время отправки"] = meta["Время отправки"]
        if meta.get("Транзит"):
            patch["Транзит"] = meta["Транзит"]

        return True, patch, None

    def build_unload_patch(self,
                           data_block: list,
                           meta: dict | None = None,
                           processed: list[bool] | None = None) -> tuple[bool, dict | None, str | None]:
        if not data_block:
            return False, None, "empty_unload_block"

        unloads = self._legacy_blocks_to_points(data_block, "Выгрузка")
        patch = {
            "unloads": unloads,
            "Выгрузка": data_block,
        }
        if processed is not None:
            real_unload_count = sum(bool(point.get("address")) for point in unloads)
            flags = ([bool(value) for value in processed] + [False] * real_unload_count)[:real_unload_count]
            patch["processed"] = flags
            patch["processed_unloads"] = flags

        return True, patch, None

    def build_task_from_buffer(
        self,
        ts_phone: str,
        ka: str,
        fio: str,
        buffer: dict,
    ) -> tuple[bool, dict | None, str | None]:
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
        loads = buffer.get("Погрузка", [])
        unloads = buffer.get("Выгрузка", [])

        task = {
            "vehicle_plate": ts,
            "driver_phone": phone,
            "driver_name": fio,
            "carrier_name": ka,
            "loads": self._legacy_blocks_to_points(loads, "Погрузка"),
            "unloads": self._legacy_blocks_to_points(unloads, "Выгрузка"),
            "ТС": ts,
            "Телефон": phone,
            "ФИО": fio,
            "КА": ka,
            "Погрузка": loads,
            "Выгрузка": unloads,
            "raw_load": str(buffer.get("raw_load") or ""),
            "raw_unload": str(buffer.get("raw_unload") or ""),
            "comm_load": str(buffer.get("comm_load") or ""),
            "comm_unload": str(buffer.get("comm_unload") or ""),
        }

        if "Время отправки" in buffer:
            task["Время отправки"] = buffer["Время отправки"]
        if "Транзит" in buffer:
            task["Транзит"] = buffer["Транзит"]

        return True, task, None

    @staticmethod
    def _legacy_blocks_to_points(blocks: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for idx, block in enumerate(blocks or [], 1):
            if not isinstance(block, dict):
                continue
            if "Комментарий" in block and not any(str(key).startswith(f"{prefix} ") for key in block):
                points.append({
                    "sequence": idx + 1000,
                    "address": "",
                    "date": "",
                    "time": "",
                    "comment": str(block.get("Комментарий") or ""),
                })
                continue

            sequence = TaskEditService._sequence_from_block(block, prefix) or idx
            points.append({
                "sequence": sequence,
                "address": str(block.get(f"{prefix} {sequence}") or ""),
                "date": str(block.get(f"Дата {sequence}") or ""),
                "time": str(block.get(f"Время {sequence}") or ""),
                "comment": str(block.get("Комментарий") or ""),
            })
        return points

    @staticmethod
    def _sequence_from_block(block: dict[str, Any], prefix: str) -> int | None:
        for key in block:
            text = str(key)
            if not text.startswith(f"{prefix} "):
                continue
            try:
                return int(text.rsplit(" ", 1)[-1])
            except ValueError:
                return None
        return None
