from __future__ import annotations

import re
from typing import Any

from Navigation_Bot.core.application.mappers.google_row_mapper import GoogleRowMapper
from Navigation_Bot.core.task_identity import google_sheet_row

""" сборка строки из Google D:H;
    определение пустой строки;
    added/updated/replaced/unchanged;
    сравнение old_row и fresh_row;
    определение переиспользованной Google-строки.
"""


class GoogleTaskMergeService:
    @staticmethod
    def build_row_from_dh(google_sheet_row_value: int, dh: list[str]) -> dict:
        return GoogleRowMapper.build_row(google_sheet_row_value, dh)

    @staticmethod
    def merge_rows_into_data(data: list, rows_map: dict[int, list[str]]) -> dict[str, int]:
        existing_google_rows = {
            google_sheet_row(row): i
            for i, row in enumerate(data)
            if isinstance(row, dict) and google_sheet_row(row) is not None
        }

        stats = {"added": 0, "updated": 0, "replaced": 0, "unchanged": 0}

        for google_sheet_row_value, dh in rows_map.items():
            if not isinstance(google_sheet_row_value, int) or not isinstance(dh, list):
                continue

            fresh = GoogleTaskMergeService.build_row_from_dh(google_sheet_row_value, dh)
            if GoogleTaskMergeService._is_empty_google_task_row(fresh):
                continue

            existing_idx = existing_google_rows.get(google_sheet_row_value)
            if existing_idx is None:
                data.append(fresh)
                existing_google_rows[google_sheet_row_value] = len(data) - 1
                stats["added"] += 1
                continue

            old_row = data[existing_idx] if 0 <= existing_idx < len(data) else {}
            if isinstance(old_row, dict) and GoogleTaskMergeService.looks_like_reused_google_row(old_row, fresh):
                data[existing_idx] = fresh
                stats["replaced"] += 1
            elif isinstance(old_row, dict):
                if not GoogleTaskMergeService.google_row_changed(old_row, fresh):
                    stats["unchanged"] += 1
                    continue
                data[existing_idx] = {**old_row, **fresh}
                stats["updated"] += 1

        return stats

    @staticmethod
    def _is_empty_google_task_row(row: dict) -> bool:
        return not any(
            [
                row.get("ТС"),
                row.get("Телефон"),
                row.get("ФИО"),
                row.get("КА"),
                row.get("Погрузка"),
                row.get("Выгрузка"),
            ]
        )

    @staticmethod
    def looks_like_reused_google_row(old_row: dict, fresh_row: dict) -> bool:
        old_plate = GoogleTaskMergeService.vehicle_signature(old_row.get("ТС"))
        new_plate = GoogleTaskMergeService.vehicle_signature(fresh_row.get("ТС"))
        old_load = GoogleTaskMergeService.signature_text(old_row.get("raw_load") or old_row.get("Погрузка"))
        new_load = GoogleTaskMergeService.signature_text(fresh_row.get("raw_load") or fresh_row.get("Погрузка"))
        old_unload = GoogleTaskMergeService.signature_text(old_row.get("raw_unload") or old_row.get("Выгрузка"))
        new_unload = GoogleTaskMergeService.signature_text(fresh_row.get("raw_unload") or fresh_row.get("Выгрузка"))
        if not old_plate or not new_plate:
            return False
        return old_plate != new_plate and (old_load != new_load or old_unload != new_unload)

    @staticmethod
    def signature_text(value: Any) -> str:
        return " ".join(str(value or "").lower().split())

    @staticmethod
    def vehicle_signature(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "").lower())

    @staticmethod
    def phone_signature(value: Any) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def google_row_changed(old_row: dict, fresh_row: dict) -> bool:
        comparable = (
            ("ТС", "ТС", GoogleTaskMergeService.vehicle_signature),
            ("Телефон", "Телефон", GoogleTaskMergeService.phone_signature),
            ("ФИО", "ФИО", GoogleTaskMergeService.signature_text),
            ("КА", "КА", GoogleTaskMergeService.signature_text),
            ("raw_load", "Погрузка", GoogleTaskMergeService.signature_text),
            ("raw_unload", "Выгрузка", GoogleTaskMergeService.signature_text),
        )
        for old_key, fresh_key, normalizer in comparable:
            old_value = old_row.get(old_key)
            if old_value is None and old_key == "raw_load":
                old_value = old_row.get("Погрузка")
            if old_value is None and old_key == "raw_unload":
                old_value = old_row.get("Выгрузка")

            if normalizer(old_value) != normalizer(fresh_row.get(fresh_key)):
                return True
        return False
