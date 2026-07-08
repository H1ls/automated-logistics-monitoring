from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtWidgets import QCompleter, QLineEdit


class CreateRaceSuggestions:
    def __init__(self, task_repository: Any, log: Callable[[str], None] | None = None):
        self.task_repository = task_repository
        self.log = log or (lambda _msg: None)

    def install(self,
                *,
                ts_editor: QLineEdit,
                carrier_editor: QLineEdit,
                driver_editor: QLineEdit,
                second_driver_editor: QLineEdit) -> None:
        self._set_completer(ts_editor, self.vehicle_suggestions())
        self._set_completer(carrier_editor, self.carrier_suggestions())
        driver_suggestions = self.driver_suggestions()
        self._set_completer(driver_editor, driver_suggestions)
        self._set_completer(second_driver_editor, driver_suggestions)

    def vehicle_suggestions(self) -> list[str]:
        rows = self._fetchall(
            """
            SELECT plate_number, monitoring_name, vehicle_full_name
            FROM vehicles
            WHERE COALESCE(plate_number, '') <> ''
               OR COALESCE(monitoring_name, '') <> ''
               OR COALESCE(vehicle_full_name, '') <> ''
            ORDER BY plate_number, monitoring_name
            LIMIT 1000
            """
        )
        values: list[str] = []
        for row in rows:
            plate = self._row_value(row, "plate_number")
            monitoring_name = self._row_value(row, "monitoring_name")
            full_name = self._row_value(row, "vehicle_full_name")
            values.extend([plate, monitoring_name, full_name])
        for row in self._repository_rows():
            values.extend([
                self._row_value(row, "vehicle_plate"),
                self._row_value(row, "ТС"),
            ])
        return self._unique_values(values)

    def carrier_suggestions(self) -> list[str]:
        rows = self._fetchall(
            """
            SELECT name
            FROM carriers
            WHERE COALESCE(name, '') <> ''
            ORDER BY name
            LIMIT 1000
            """
        )
        values = [self._row_value(row, "name") for row in rows]
        for row in self._repository_rows():
            values.extend([
                self._row_value(row, "carrier_name"),
                self._row_value(row, "КА"),
            ])
        return self._unique_values(values)

    def driver_suggestions(self) -> list[str]:
        rows = self._fetchall(
            """
            SELECT full_name
            FROM drivers
            WHERE COALESCE(full_name, '') <> ''
            ORDER BY full_name
            LIMIT 1000
            """
        )
        values = [self._row_value(row, "full_name") for row in rows]
        for row in self._repository_rows():
            values.extend([
                self._row_value(row, "driver_name"),
                self._row_value(row, "ФИО"),
            ])
        return self._unique_values(values)

    def _set_completer(self, editor: QLineEdit, values: list[str]) -> None:
        if not values:
            return
        completer = QCompleter(editor)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(12)
        completer.setCompletionPrefix("")
        completer.setCompletionColumn(0)
        completer.setModel(QStringListModel(values, completer))
        editor.setCompleter(completer)

    def _repository_rows(self) -> list[Any]:
        try:
            getter = getattr(self.task_repository, "get", None)
            rows = getter() if callable(getter) else getattr(self.task_repository, "data", None)
            return list(rows or []) if isinstance(rows, list) else []
        except Exception as exc:
            self.log(f"[DEBUG] Не удалось загрузить подсказки из текущих строк: {exc}")
            return []

    def _fetchall(self, query: str) -> list[Any]:
        connection = getattr(self.task_repository, "connection", None)
        if connection is None:
            return []
        try:
            return list(connection.execute(query).fetchall())
        except Exception as exc:
            self.log(f"[DEBUG] Не удалось загрузить подсказки CreateRaceDialog: {exc}")
            return []

    @staticmethod
    def _row_value(row: Any, key: str) -> str:
        if isinstance(row, dict):
            return str(row.get(key) or "").strip()
        try:
            return str(row[key] or "").strip()
        except (KeyError, TypeError, IndexError):
            return ""

    @staticmethod
    def _unique_values(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            key = normalized.casefold()
            if normalized and key not in seen:
                seen.add(key)
                result.append(normalized)
        return result
