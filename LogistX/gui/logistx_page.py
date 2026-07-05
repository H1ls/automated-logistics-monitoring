from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QMenu, QPushButton, QTableWidget, QVBoxLayout, QWidget)

from LogistX.controllers.oneC_report_importer import OneCReportImporter
from LogistX.gui.logistx_table_renderer import LogistXTableRenderer
from LogistX.services.logistx_data_service import LogistXDataService
from Navigation_Bot.gui.dialogs.sites_db_editor_dialog import SitesDbEditorDialog
from Navigation_Bot.core.logging import normalize_log_func


class CounterpartyFilterDialog(QDialog):
    def __init__(self, counterparties: list[str], selected: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Фильтр контрагентов")
        self.resize(320, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Контрагенты из текущего logistx_sample.json:"))

        self.list_widget = QListWidget()
        for name in counterparties:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if not selected or name in selected else Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.Reset)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self.clear_selection)
        layout.addWidget(buttons)

    def selected_counterparties(self) -> set[str]:
        selected = set()
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item.checkState() == Qt.CheckState.Checked:
                selected.add(item.text())
        return selected

    def clear_selection(self) -> None:
        for idx in range(self.list_widget.count()):
            self.list_widget.item(idx).setCheckState(Qt.CheckState.Unchecked)


class LogistXPage(QWidget):
    COL_FROM = LogistXTableRenderer.COL_FROM
    COL_TO = LogistXTableRenderer.COL_TO

    fact_clicked = pyqtSignal(int)

    def __init__(self, parent=None, log_func=print):
        super().__init__(parent)
        self.log = normalize_log_func(log_func)
        self.rows: list[dict] = []
        self.view_order: list[int] = []
        self.hidden_row_keys: set[tuple[str, str, str, str]] = set()
        self.show_hidden_rows = False
        self.selected_counterparties: set[str] = set()

        self.data_service = LogistXDataService(log_func=self.log)

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_toolbar())

        self.table = QTableWidget(0, 8)
        layout.addWidget(self.table)

        self.renderer = LogistXTableRenderer(self.table, log_func=self.log)
        self.renderer.setup()
        self.renderer.set_on_play_clicked(self.fact_clicked.emit)

        self.btn_refresh.clicked.connect(self.load_sample)
        self.btn_import_1c.clicked.connect(self.import_from_1c_rdp)
        self.btn_filter.clicked.connect(self.open_counterparty_filter)
        self.btn_hide_marked.clicked.connect(self.toggle_hidden_rows_visibility)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_row_context_menu)
        self._update_hide_button_text()

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить")
        toolbar.addWidget(self.btn_refresh)

        self.btn_import_1c = QPushButton("Импорт из 1С (RDP)")
        toolbar.addWidget(self.btn_import_1c)

        self.btn_filter = QPushButton("Фильтр")
        toolbar.addWidget(self.btn_filter)

        self.btn_hide_marked = QPushButton("Скрыть")
        toolbar.addWidget(self.btn_hide_marked)

        toolbar.addStretch(1)
        return toolbar

    def load_sample(self) -> None:
        rows = self.data_service.load_rows()
        if not rows:
            return

        self.set_rows(rows)
        self.log(f"✅ LogistX: загружено рейсов: {len(rows)}")

    def save_rows(self) -> None:
        self.data_service.save_rows(self.rows)

    def set_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.selected_counterparties &= set(self._counterparties())
        self._drop_stale_hidden_keys()
        self._refresh_table()

    def on_cell_double_clicked(self, row: int, col: int) -> None:
        if col not in (self.COL_FROM, self.COL_TO):
            return

        source_idx = self._source_index_for_visual_row(row)
        if source_idx is None:
            return

        address = self._extract_raw_address(source_idx, col).strip()
        if not address:
            return

        dialog = SitesDbEditorDialog(parent=self, prefill_address=address, log_func=self.log)
        dialog.exec()

        self.renderer.reload_sites_db()
        self.renderer.update_address_cell(source_idx, col, address)

    def build_close_race_job(self, row: int) -> dict | None:
        return self.renderer.build_close_race_job(row, self.rows)

    def apply_close_race_result(self, row: int, ctx, result: dict) -> None:
        try:
            changed = self.renderer.apply_close_race_result(row, self.rows, ctx, result)
            if changed:
                self.save_rows()
        except Exception as e:
            self.log(f"❌ LogistX apply_close_race_result: {e}")

    def import_from_1c_rdp(self) -> None:
        importer = OneCReportImporter(log_func=self.log)
        importer.run()
        self.load_sample()

    def open_counterparty_filter(self) -> None:
        counterparties = self._counterparties()
        dialog = CounterpartyFilterDialog(counterparties, self.selected_counterparties, parent=self)
        if not dialog.exec():
            return

        selected = dialog.selected_counterparties()
        self.selected_counterparties = selected if selected != set(counterparties) else set()
        self._refresh_table()

    def open_row_context_menu(self, pos) -> None:
        visual_row = self.table.rowAt(pos.y())
        source_idx = self._source_index_for_visual_row(visual_row)
        if source_idx is None:
            return

        menu = QMenu(self.table)
        row_key = self._row_key(self.rows[source_idx])
        action_hide = menu.addAction("Снять скрытие" if row_key in self.hidden_row_keys else "Скрыть")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == action_hide:
            if row_key in self.hidden_row_keys:
                self.hidden_row_keys.remove(row_key)
                self.log(f"👁 LogistX: скрытие снято со строки: {source_idx + 1}")
            else:
                self.hidden_row_keys.add(row_key)
                self.log(f"🙈 LogistX: строка скрыта: {source_idx + 1}")
            self._refresh_table()

    def toggle_hidden_rows_visibility(self) -> None:
        if not self.hidden_row_keys:
            return

        self.show_hidden_rows = not self.show_hidden_rows
        self._refresh_table()

    def _extract_raw_address(self, row: int, col: int) -> str:
        if row < 0 or row >= len(self.rows):
            return ""

        obj = self.rows[row] or {}
        if col == self.COL_FROM:
            return self._first_value(obj, "Рейс.Пункт отправления", "Пункт отправления", "Отправление")
        if col == self.COL_TO:
            return self._first_value(obj, "Рейс.Пункт назначения", "Пункт назначения", "Назначение")
        return ""

    def _refresh_table(self) -> None:
        self.view_order = self._build_view_order()
        self.renderer.render_entries([(idx, self.rows[idx]) for idx in self.view_order])
        self.renderer.mark_hidden_rows(self._visible_hidden_indexes())
        self._update_hide_button_text()

    def _build_view_order(self) -> list[int]:
        indexes = []
        for idx, row in enumerate(self.rows):
            is_hidden = self._row_key(row) in self.hidden_row_keys
            if is_hidden and not self.show_hidden_rows:
                continue
            if self.selected_counterparties and self._counterparty(row) not in self.selected_counterparties:
                continue
            indexes.append(idx)
        return indexes

    def _source_index_for_visual_row(self, visual_row: int) -> int | None:
        if visual_row < 0 or visual_row >= len(self.view_order):
            return None
        return self.view_order[visual_row]

    def _counterparties(self) -> list[str]:
        names = {self._counterparty(row) for row in self.rows}
        names.discard("")
        return sorted(names, key=str.casefold)

    def _update_hide_button_text(self) -> None:
        count = len(self.hidden_row_keys)
        if self.show_hidden_rows:
            self.btn_hide_marked.setText(f"Скрыть скрытые ({count})")
        else:
            self.btn_hide_marked.setText(f"Показать скрытые ({count})" if count else "Скрыть")
        self.btn_hide_marked.setEnabled(bool(count))

    def _visible_hidden_indexes(self) -> set[int]:
        if not self.show_hidden_rows:
            return set()
        return {idx for idx in self.view_order if self._row_key(self.rows[idx]) in self.hidden_row_keys}

    def _drop_stale_hidden_keys(self) -> None:
        active_keys = {self._row_key(row) for row in self.rows}
        self.hidden_row_keys &= active_keys
        if not self.hidden_row_keys:
            self.show_hidden_rows = False

    @classmethod
    def _row_key(cls, row: dict) -> tuple[str, str, str, str]:
        return (
            str(row.get("Рейс") or "").strip(),
            str(row.get("ТС") or "").strip(),
            cls._counterparty(row),
            str(row.get("Плановая дата освобождения разгрузка") or "").strip(),
        )

    @staticmethod
    def _counterparty(row: dict) -> str:
        return str(row.get("Контрагент") or row.get("КА") or "").strip()

    @staticmethod
    def _first_value(obj: dict, *keys: str) -> str:
        for key in keys:
            value = obj.get(key)
            if value:
                return str(value)
        return ""
