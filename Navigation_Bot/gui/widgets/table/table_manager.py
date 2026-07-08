from PyQt6.QtCore import QTimer

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QLabel

from Navigation_Bot.gui.dialogs.components.combined_settings_tabs import VerticalTextDelegate
from Navigation_Bot.gui.widgets.table.row_action_controller import RowActionController
from Navigation_Bot.gui.widgets.table.table_display_formatter import TableDisplayFormatter
from Navigation_Bot.gui.widgets.table.table_row_renderer import TableRowRenderer
from Navigation_Bot.core.domain.task_identity import row_identity_for_gui
from Navigation_Bot.core.logging import normalize_log_func


class TableManager:
    def __init__(self, table_widget, task_repository, log_func, on_row_click, on_edit_id_click,
                 editable_field_workflow=None, address_edit_workflow=None, reload_callback=None):

        self.task_repository = task_repository
        self.table = table_widget
        self.log = normalize_log_func(log_func)
        self.on_row_click = on_row_click
        self.on_edit_id_click = on_edit_id_click
        self.address_edit_workflow = address_edit_workflow
        self.editable_field_workflow = editable_field_workflow
        self.reload_callback = reload_callback

        self.formatter = TableDisplayFormatter(log_func=self.log)
        self._editable_headers = {"Телефон", "ФИО", "КА", "id"}
        self.after_display = None
        self.view_order = []

        # Делегат для вертикального текста в колонке "КА" (индекс 3)
        self._vertical_delegate = VerticalTextDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._vertical_delegate)

        self.row_action_controller = RowActionController()
        self.row_renderer = TableRowRenderer(table=self.table,
                                             log_func=self.log,
                                             formatter=self.formatter,
                                             row_action_controller=self.row_action_controller,
                                             on_row_click=self.on_row_click,
                                             on_edit_id_click=self.on_edit_id_click, )
        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.table)
        self._copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._copy_shortcut.activated.connect(self.copy_selected_rows)
        self.table.verticalHeader().sectionClicked.connect(self.select_visual_row)

    def apply_settings(self, settings: dict):
        self.row_renderer.apply_settings(settings or {})

    def set_on_row_click(self, callback):
        self.on_row_click = callback
        self.row_renderer.on_row_click = callback

    # ---- A. display orchestration
    def display(self, reload_from_file=True, view_order=None):
        self._reload_context(reload_from_file)
        self.formatter.reload_sites_db()
        rows = self.task_repository.get() or []

        # стопаем все спиннеры перед перерисовкой таблицы (иначе они "висят" между display)
        self.row_action_controller.clear()

        if view_order is None:
            view_order = list(range(len(rows)))
        self.view_order = view_order or list(range(len(rows)))
        self._row_identity_to_visual = {}

        for visual_row, real_idx in enumerate(self.view_order):
            try:
                key = row_identity_for_gui(rows[real_idx] or {})
            except Exception:
                key = None
            if key is not None:
                self._row_identity_to_visual[key] = visual_row

        scroll_value, selected_row = self._capture_view_state()

        try:
            self.table.blockSignals(True)
            self._dispose_cell_widgets()
            self.table.setRowCount(0)
            self._render_all_rows(rows, view_order)
            self.table.resizeRowsToContents()

        finally:
            self.table.blockSignals(False)
            QTimer.singleShot(0, lambda: self._restore_scroll(scroll_value, selected_row))

        if callable(self.after_display):
            self.after_display()

    def _dispose_cell_widgets(self) -> None:
        """Hide embedded widgets before Qt detaches them while rows are reset."""
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, column)
                if widget is None:
                    continue
                widget.hide()
                self.table.removeCellWidget(row, column)
                widget.deleteLater()

    def _reload_context(self, reload_from_file: bool):
        # Вспомогательные методы для display()
        """Перечитывает DataContext при необходимости"""
        if not reload_from_file:
            return
        try:
            self.task_repository.reload()
        except Exception as e:
            self.log(f"❌ Ошибка при загрузке данных задач: {e}")

    def _capture_view_state(self):
        """Запоминает положение скролла и выделенную строку"""
        try:
            scroll_value = self.table.verticalScrollBar().value()
            selected_row = self.table.currentRow()
        except Exception as e:
            self.log(f"{e}")
            scroll_value, selected_row = 0, -1
        return scroll_value, selected_row

    def _render_all_rows(self, rows: list[dict], view_order):
        """Передает отрисовывать все обычные строки таблицы в TableRowRenderer"""
        for visual_row, real_idx in enumerate(view_order):
            if not (0 <= real_idx < len(rows)):
                continue

            row = rows[real_idx]
            self.row_renderer.render_row(row_idx=visual_row, row=row, real_idx=real_idx, )

    def _visual_to_real(self, visual_row: int) -> int | None:
        if visual_row < 0 or visual_row >= len(self.view_order):
            return None
        real_idx = self.view_order[visual_row]
        return real_idx if real_idx >= 0 else None

    def visual_row_by_row_identity(self, row_identity):
        return self._row_identity_to_visual.get(row_identity, -1)

    def visual_row_by_index_key(self, key):
        return self.visual_row_by_row_identity(key)

    # ---- B. table event entrypoints
    def edit_cell_content(self, row, col):
        try:
            header_item = self.table.horizontalHeaderItem(col)
            if not header_item:
                return

            if not self.address_edit_workflow:
                self.log("⚠️ AddressEditWorkflowService не подключён")
                return

            real_idx = self._visual_to_real(row)
            if real_idx is None:
                return

            ok, updated_row, err = self.address_edit_workflow.edit_address(
                real_idx=real_idx,
                col_name=header_item.text(),
                parent=self.table,
            )

            if not ok:
                if err not in ("unsupported_column", "cancelled"):
                    self.log(f"⚠️ Не удалось обновить адрес в строке {row + 1}: {err}")
                return

            if callable(self.reload_callback):
                self.reload_callback()
            else:
                self.display()

        except Exception as e:
            self.log(f"❌ TableManager.edit_cell_content: {e}")

    def save_table_item_on_edit(self, item):
        QTimer.singleShot(0, lambda: self._save_item(item))

    # ---- D.facades to child helpers
    def set_row_busy(self, row_identity: int, busy: bool):
        self.row_action_controller.set_row_busy(row_identity, busy)

    def set_all_rows_busy(self, busy: bool):
        self.row_action_controller.set_all_rows_busy(busy)

    def select_visual_row(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)

    def copy_selected_rows(self) -> None:
        focus_widget = QApplication.focusWidget()
        if focus_widget is not None and focus_widget not in (self.table, self.table.viewport()):
            copy = getattr(focus_widget, "copy", None)
            if callable(copy):
                copy()
            return

        indexes = [index for index in self.table.selectedIndexes() if self._is_copyable_column(index.column())]
        if not indexes and self.table.currentRow() >= 0:
            self._copy_rows([self.table.currentRow()])
            return

        if len(indexes) == 1:
            self._copy_rows([indexes[0].row()])
            return

        copyable_columns = self._copyable_columns()
        selected_by_row = {}
        for index in indexes:
            selected_by_row.setdefault(index.row(), set()).add(index.column())

        rows = sorted(selected_by_row)
        full_rows_selected = all(selected_by_row[row] >= set(copyable_columns) for row in rows)
        if full_rows_selected:
            self._copy_rows(rows)
            return

        self._copy_cell_range(indexes)

    def _copy_rows(self, rows: list[int]) -> None:
        copied_rows = []
        for row in rows:
            values = [self._cell_text(row, column) for column in self._copyable_columns()]
            copied_rows.append("\t".join(values))

        self._set_clipboard_rows(copied_rows)

    def _copy_cell_range(self, indexes) -> None:
        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes if self._is_copyable_column(index.column())})
        selected = {(index.row(), index.column()) for index in indexes}

        copied_rows = []
        for row in rows:
            values = []
            for column in columns:
                values.append(self._cell_text(row, column) if (row, column) in selected else "")
            copied_rows.append("\t".join(values))

        self._set_clipboard_rows(copied_rows)

    def _set_clipboard_rows(self, copied_rows: list[str]) -> None:
        text = "\n".join(copied_rows).strip()
        if text:
            QApplication.clipboard().setText(text)

    def _copyable_columns(self) -> list[int]:
        return [column for column in range(self.table.columnCount()) if self._is_copyable_column(column)]

    def _is_copyable_column(self, column: int) -> bool:
        return column != 0 and not self.table.isColumnHidden(column)

    def _cell_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        if item is not None:
            return item.text()

        widget = self.table.cellWidget(row, column)
        if widget is None:
            return ""

        label = widget.findChild(QLabel)
        if label is not None:
            return label.text()

        return ""

    def _restore_scroll(self, scroll_value, selected_row):
        try:
            self.table.verticalScrollBar().setValue(scroll_value)
            if 0 <= selected_row < self.table.rowCount():
                self.table.selectRow(selected_row)
        except Exception as e:
            self.log(f"❌ Ошибка при восстановлении позиции: {e}")

    def _save_item(self, item):
        if getattr(self, "_block_item_save", False):
            return

        row = item.row()
        col = item.column()

        header_item = self.table.horizontalHeaderItem(col)
        if not header_item:
            return
        header = header_item.text()

        if header not in self._editable_headers:
            return

        if not self.editable_field_workflow:
            self.log("⚠️ EditableFieldWorkflowService не подключён")
            return

        real_idx = self._visual_to_real(row)
        if real_idx is None:
            return

        ok, updated_row, err = self.editable_field_workflow.save_field(real_idx=real_idx,
                                                                       header=header,
                                                                       value=item.text(), )
        if ok:
            return

        if err == "invalid_id":
            self.log(f"⚠️ Неверный ID в строке {row + 1}")
        elif err == "empty_id":
            self.log(f"⚠️ Пустой ID в строке {row + 1}")
        else:
            self.log(f"⚠️ Не удалось сохранить изменение в строке {row + 1}: {err}")
