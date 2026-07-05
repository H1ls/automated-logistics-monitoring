import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import QComboBox, QDialog, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from LogistX.config.paths import SITES_DB_FILE
from Navigation_Bot.gui.dialogs.aliases_editor_dialog import AliasesEditorDialog
from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog
from Navigation_Bot.gui.widgets.global_search_bar import GlobalSearchBar

SITES_DB_PATH = SITES_DB_FILE

COL_ADDRESS = 0
COL_SITE_ID = 1
COL_GEOFENCE = 2
COL_TYPE = 3
COL_ALIASES = 4

HEADERS = ["Адрес", "site_id", "geofence", "type", "aliases"]
ALIASES_ROLE = Qt.ItemDataRole.UserRole.value
SECTION_ROLE = ALIASES_ROLE + 1
TYPE_VALUES = ("Any", "Load", "Upload")


# TODO: Перенести SITES_DB_FILE из json в BD, json как резерв.
class SitesDbEditorDialog(BaseDialog):
    def __init__(self, parent=None, prefill_address: str = "", log_func=None):
        super().__init__(title="Редактор геозон/складов", size=(980, 850), parent=parent, log_func=log_func)
        self.prefill_address = (prefill_address or "").strip()
        self._loading = False
        self._marking_duplicates = False

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.search_bar = GlobalSearchBar(self.table, self.log, self)
        self.search_bar.set_cell_text_provider(self._cell_search_text)
        self.search_bar.set_row_filter(lambda row: not self._is_section_row(row))
        self.search_bar.hide()
        self.root.addWidget(self.search_bar)
        self.root.addWidget(self.table)

        self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_ADDRESS, 470)
        self.table.setColumnWidth(COL_SITE_ID, 150)
        self.table.setColumnWidth(COL_GEOFENCE, 170)
        self.table.setColumnWidth(COL_TYPE, 75)
        self.table.setColumnWidth(COL_ALIASES, 46)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.btn_add = self.make_button("➕ Добавить", self.add_row)
        self.btn_del = self.make_button("🗑 Удалить", self.delete_selected_rows)
        self.btn_save = self.make_button("💾 Сохранить", self.save_json)
        self.btn_close = self.make_button("Закрыть", self.close)
        self.add_button_row(left=(self.btn_add, self.btn_del),
                            right=(self.btn_save, self.btn_close))

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.root.addWidget(self.status_label)

        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.itemChanged.connect(self._on_item_changed)

        self._shortcut_find = QShortcut(QKeySequence.StandardKey.Find, self)
        self._shortcut_find.activated.connect(self.search_bar.start)

        self.load_json()
        if self.prefill_address:
            self._add_prefill_row(self.prefill_address)

    def _norm(self, s: str) -> str:
        return (s or "").strip().lower().replace("ё", "е")

    def _sort_key(self, obj: dict):
        return (self._norm(obj.get("address", "")),
                self._norm(obj.get("geofence", "")),
                self._norm(obj.get("site_id", "")))

    def _address_group(self, address: str) -> str:
        text = (address or "").strip()
        if not text:
            return "Новые"
        first = text[0].upper()
        return first if first.isalnum() else "#"

    def _is_section_row(self, row: int) -> bool:
        item = self.table.item(row, COL_ADDRESS)
        return bool(item and item.data(SECTION_ROLE))

    def _append_section_row(self, group: str) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        item = QTableWidgetItem(f"  {group}")
        item.setData(SECTION_ROLE, True)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setBackground(QBrush(QColor("#e8edf3")))
        self.table.setItem(row, COL_ADDRESS, item)
        self.table.setSpan(row, COL_ADDRESS, 1, len(HEADERS))
        self.table.setRowHeight(row, 24)
        return row

    def _find_group_insert_row(self, group: str) -> int:
        section_row = None
        for row in range(self.table.rowCount()):
            if not self._is_section_row(row):
                continue
            if self.table.item(row, COL_ADDRESS).text().strip() == group:
                section_row = row
                break

        if section_row is None:
            self._append_section_row(group)
            return self.table.rowCount()

        row = section_row + 1
        while row < self.table.rowCount() and not self._is_section_row(row):
            row += 1
        return row

    def _aliases_for_row(self, row: int) -> list[str]:
        item = self.table.item(row, COL_ALIASES)
        aliases = item.data(ALIASES_ROLE) if item is not None else []
        return list(aliases or []) if isinstance(aliases, list) else []

    def _append_unique_alias(self, aliases: list[str], value: str, primary_address: str = "") -> None:
        value = (value or "").strip()
        if not value:
            return

        value_key = self._norm(value)
        if primary_address and value_key == self._norm(primary_address):
            return

        existing = {self._norm(alias) for alias in aliases}
        if value_key not in existing:
            aliases.append(value)

    def _set_aliases_for_row(self, row: int, aliases: list[str]) -> None:
        item = self.table.item(row, COL_ALIASES)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, COL_ALIASES, item)
        clean = [str(alias).strip() for alias in aliases if str(alias).strip()]
        item.setData(ALIASES_ROLE, clean)
        item.setText(f"✎ {len(clean)}" if clean else "✎")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setBackground(QBrush(QColor("#eef6ff")))
        # item.setToolTip(
        #     "Двойной клик для редактирования aliases"
        #     + (f"\n\n{chr(10).join(clean)}" if clean else "")
        # )
        item.setToolTip("Двойной клик для редактирования aliases" + (f"\n\n{chr(10).join(clean)}" if clean else ""))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.search_bar.refresh()

    def _set_type_for_row(self, row: int, value: str) -> None:
        combo = QComboBox(self.table)
        combo.addItems(TYPE_VALUES)
        normalized = (value or "").strip()
        if not normalized:
            normalized = "Any"
        if normalized not in TYPE_VALUES:
            combo.addItem(normalized)
        combo.setCurrentText(normalized)
        self.table.setCellWidget(row, COL_TYPE, combo)
        item = QTableWidgetItem(normalized)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL_TYPE, item)
        combo.currentTextChanged.connect(lambda text, item=item: self._on_type_changed(item, text))

    def _type_for_row(self, row: int) -> str:
        widget = self.table.cellWidget(row, COL_TYPE)
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return (self.table.item(row, COL_TYPE).text() if self.table.item(row, COL_TYPE) else "").strip()

    def _on_type_changed(self, item: QTableWidgetItem, text: str) -> None:
        item.setText(text)
        self.search_bar.refresh()

    def _cell_search_text(self, row: int, col: int) -> str:
        if col == COL_TYPE:
            return self._type_for_row(row)
        if col == COL_ALIASES:
            return " ".join(self._aliases_for_row(row))
        item = self.table.item(row, col)
        return item.text() if item is not None else ""

    def edit_aliases(self, row: int):
        if self._is_section_row(row):
            return

        dlg = AliasesEditorDialog(self, self._aliases_for_row(row))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._set_aliases_for_row(row, dlg.get_aliases())

    def on_cell_double_clicked(self, row: int, col: int):
        if col == COL_ALIASES:
            self.edit_aliases(row)

    def load_json(self):
        self._loading = True
        try:
            self.table.setRowCount(0)
            if not SITES_DB_PATH.exists():
                self._update_duplicate_geofence_marks()
                return

            data = json.loads(SITES_DB_PATH.read_text(encoding="utf-8") or "[]")
            if not isinstance(data, list):
                data = []
            data.sort(key=self._sort_key)

            current_group = None
            for obj in data:
                group = self._address_group(str(obj.get("address", "") or ""))
                if group != current_group:
                    self._append_section_row(group)
                    current_group = group
                self._append_obj(obj)

            self.table.resizeRowsToContents()
        except Exception as e:
            self.log(f"❌ Ошибка загрузки sites_db.json: {e}")
        finally:
            self._loading = False
            self._update_duplicate_geofence_marks()
            self.search_bar.refresh()

    def _append_obj(self, obj: dict):
        self._insert_obj(self.table.rowCount(), obj)

    def _insert_obj(self, row: int, obj: dict):
        self.table.insertRow(row)
        values = [
            str(obj.get("address", "") or ""),
            str(obj.get("site_id", "") or ""),
            str(obj.get("geofence", "") or ""),
        ]
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(value))
        self._set_type_for_row(row, str(obj.get("type", "") or "Any"))

        aliases_list = obj.get("aliases", []) or []
        if not isinstance(aliases_list, list):
            aliases_list = []
        self._set_aliases_for_row(row, aliases_list)

    def add_row(self, address: str = ""):
        group = self._address_group(address)
        row = self._find_group_insert_row(group)
        self._insert_obj(row, {"address": address})
        self.table.setCurrentCell(row, COL_ADDRESS)
        self.table.resizeRowsToContents()
        self._update_duplicate_geofence_marks()
        self.search_bar.refresh()

    def _add_prefill_row(self, address: str) -> None:
        self._insert_obj(0, {"address": address})
        self.table.setCurrentCell(0, COL_SITE_ID)
        self.table.scrollToTop()
        self.table.resizeRowsToContents()
        self._update_duplicate_geofence_marks()
        self.search_bar.refresh()

    def delete_selected_rows(self):
        rows_to_delete = sorted({i.row() for i in self.table.selectedIndexes()
                                 if not self._is_section_row(i.row())}, reverse=True)
        if not rows_to_delete:
            return

        for row in rows_to_delete:
            self.table.removeRow(row)
        self._remove_empty_sections()
        self._update_duplicate_geofence_marks()
        self.search_bar.refresh()

    def _remove_empty_sections(self) -> None:
        for row in range(self.table.rowCount() - 1, -1, -1):
            if not self._is_section_row(row):
                continue
            next_row = row + 1
            if next_row >= self.table.rowCount() or self._is_section_row(next_row):
                self.table.removeRow(row)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._marking_duplicates:
            return
        if item.column() == COL_GEOFENCE:
            self._update_duplicate_geofence_marks()
        self.search_bar.refresh()

    def _update_duplicate_geofence_marks(self) -> None:
        self._marking_duplicates = True
        try:
            rows_by_geofence: dict[str, list[int]] = {}
            for row in range(self.table.rowCount()):
                if self._is_section_row(row):
                    continue
                geofence = (self.table.item(row, COL_GEOFENCE).text()
                            if self.table.item(row, COL_GEOFENCE) else "").strip()
                key = self._norm(geofence)
                if key:
                    rows_by_geofence.setdefault(key, []).append(row)

            duplicate_groups = {key: rows for key, rows in rows_by_geofence.items() if len(rows) > 1}
            duplicate_rows = {row for rows in duplicate_groups.values() for row in rows}

            duplicate_brush = QBrush(QColor("#fff0a6"))
            clear_brush = QBrush()
            for row in range(self.table.rowCount()):
                if self._is_section_row(row):
                    continue
                item = self.table.item(row, COL_GEOFENCE)
                if item is None:
                    continue
                if row in duplicate_rows:
                    item.setBackground(duplicate_brush)
                    item.setToolTip("Одинаковый geofence встречается в нескольких адресах")
                else:
                    item.setBackground(clear_brush)
                    item.setToolTip("")

            if duplicate_groups:
                details = []
                for rows in duplicate_groups.values():
                    geofence = self.table.item(rows[0], COL_GEOFENCE).text().strip()
                    details.append(f"- {geofence} ×{len(rows)}")
                self.status_label.setText(
                    "Одинаковые geofence. При сохранении лишние адреса уйдут в aliases:\n"
                    + "\n".join(details)
                )
                self.status_label.setStyleSheet("color: #9a6500;")
            else:
                self.status_label.setText("Одинаковые geofence не найдены")
                self.status_label.setStyleSheet("color: #3f7f3f;")
        finally:
            self._marking_duplicates = False

    # TODO: Анимация сохранение, либо ускорить сохранение
    # TODO: Закрывать окно после сохранения
    def save_json(self):
        try:
            data = []
            for row in range(self.table.rowCount()):
                if self._is_section_row(row):
                    continue

                address = (self.table.item(row, COL_ADDRESS).text() if self.table.item(row, COL_ADDRESS) else "").strip()
                site_id = (self.table.item(row, COL_SITE_ID).text() if self.table.item(row, COL_SITE_ID) else "").strip()
                geofence = (self.table.item(row, COL_GEOFENCE).text() if self.table.item(row, COL_GEOFENCE) else "").strip()
                typ = self._type_for_row(row)
                aliases = self._aliases_for_row(row)

                if not self._has_save_payload(site_id, geofence, typ, aliases):
                    continue

                data.append({"address": address,
                             "site_id": site_id,
                             "geofence": geofence,
                             "type": typ,
                             "aliases": aliases})
            data, merged_count = self._merge_duplicate_geofences(data)
            data.sort(key=self._sort_key)
            SITES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            SITES_DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.load_json()
            message = "sites_db.json успешно сохранён."
            if merged_count:
                message += f"\nАдресов перенесено в aliases по одинаковому geofence: {merged_count}."
            self.info("Сохранено", message)
        except Exception as e:
            self.error("Ошибка", f"Не удалось сохранить: {e}")

    def _has_save_payload(self, site_id: str, geofence: str, typ: str, aliases: list[str]) -> bool:
        return any([site_id, geofence, aliases, typ and typ != "Any"])

    def _merge_duplicate_geofences(self, data: list[dict]) -> tuple[list[dict], int]:
        merged: list[dict] = []
        by_geofence: dict[str, dict] = {}
        merged_count = 0

        for obj in data:
            geofence_key = self._norm(obj.get("geofence", ""))
            if not geofence_key:
                merged.append(obj)
                continue

            existing = by_geofence.get(geofence_key)
            if existing is None:
                aliases = obj.get("aliases", [])
                obj["aliases"] = [str(alias).strip() for alias in aliases if str(alias).strip()]
                by_geofence[geofence_key] = obj
                merged.append(obj)
                continue

            primary_address = str(existing.get("address") or "")
            duplicate_address = str(obj.get("address") or "")
            existing_aliases = existing.setdefault("aliases", [])
            self._append_unique_alias(existing_aliases, duplicate_address, primary_address)
            for alias in obj.get("aliases", []) or []:
                self._append_unique_alias(existing_aliases, str(alias), primary_address)

            if not existing.get("site_id") and obj.get("site_id"):
                existing["site_id"] = obj["site_id"]
            if not existing.get("type") and obj.get("type"):
                existing["type"] = obj["type"]

            merged_count += 1

        return merged, merged_count
