from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QTableWidgetItem, QPushButton)

from Navigation_Bot.gui.dialogs.combinedSettingsDialog import VerticalTextDelegate
from Navigation_Bot.gui.widgets.table.row_action_controller import RowActionController
from Navigation_Bot.gui.widgets.table.table_display_formatter import TableDisplayFormatter
from Navigation_Bot.gui.widgets.table.table_row_renderer import TableRowRenderer


class TableManager:
    def __init__(self, table_widget, data_context, log_func, on_row_click, on_edit_id_click,
                 new_task_workflow=None, editable_field_workflow=None,
                 address_edit_workflow=None, reload_callback=None):

        self.data_context = data_context
        self.table = table_widget
        self.log = log_func
        self.on_row_click = on_row_click
        self.on_edit_id_click = on_edit_id_click
        self.new_task_workflow = new_task_workflow
        self.address_edit_workflow = address_edit_workflow
        self.editable_field_workflow = editable_field_workflow
        self.reload_callback = reload_callback

        self.formatter = TableDisplayFormatter()
        self._new_entry_buffer = {}
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

    # ---- A. display orchestration
    def display(self, reload_from_file=True, view_order=None):
        self._reload_context(reload_from_file)
        json_data = self.data_context.get() or []

        # стопаем все спиннеры перед перерисовкой таблицы (иначе они "висят" между display)
        self.row_action_controller.clear()

        if view_order is None:
            view_order = list(range(len(json_data)))
        self.view_order = view_order or list(range(len(json_data)))
        self._index_to_visual = {}

        for visual_row, real_idx in enumerate(self.view_order):
            try:
                key = (json_data[real_idx] or {}).get("index")
            except Exception:
                key = None
            if key is not None:
                self._index_to_visual[key] = visual_row

        scroll_value, selected_row = self._capture_view_state()

        try:
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            self._render_all_rows(json_data, view_order)
            self.table.resizeRowsToContents()
            self._add_new_entry_row()

        finally:
            self.table.blockSignals(False)
            QTimer.singleShot(0, lambda: self._restore_scroll(scroll_value, selected_row))

        if callable(self.after_display):
            self.after_display()

    def _reload_context(self, reload_from_file: bool):
        # Вспомогательные методы для display()
        """Перечитывает DataContext при необходимости"""
        if not reload_from_file:
            return
        try:
            self.data_context.reload()
        except Exception as e:
            self.log(f"❌ Ошибка при загрузке JSON: {e}")

    def _capture_view_state(self):
        """Запоминает положение скролла и выделенную строку"""
        try:
            scroll_value = self.table.verticalScrollBar().value()
            selected_row = self.table.currentRow()
        except Exception as e:
            self.log(f"{e}")
            scroll_value, selected_row = 0, -1
        return scroll_value, selected_row

    def _render_all_rows(self, json_data: list[dict], view_order):
        """Передает отрисовывать все обычные строки таблицы в TableRowRenderer"""
        for visual_row, real_idx in enumerate(view_order):
            if not (0 <= real_idx < len(json_data)):
                continue

            row = json_data[real_idx]
            self.row_renderer.render_row(row_idx=visual_row, row=row, real_idx=real_idx, )

    def _visual_to_real(self, visual_row: int) -> int | None:
        if visual_row < 0 or visual_row >= len(self.view_order):
            return None
        real_idx = self.view_order[visual_row]
        return real_idx if real_idx >= 0 else None

    def visual_row_by_index_key(self, key):
        return self._index_to_visual.get(key, -1)

    # ---- B. table event entrypoints
    def edit_cell_content(self, row, col):
        try:
            header_item = self.table.horizontalHeaderItem(col)
            if not header_item:
                return

            if not self.address_edit_workflow:
                self.log("⚠️ AddressEditWorkflowService не подключён")
                return

            col_name = header_item.text()
            prefix = self.address_edit_workflow.resolve_prefix(col_name)
            if not prefix:
                return

            is_new_entry_row = row >= len(self.view_order) or row >= self.table.rowCount() - 1

            if is_new_entry_row:
                self._handle_new_entry_edit(row=row, col=col, prefix=prefix)
            else:
                self._handle_existing_entry_edit(row=row, prefix=prefix)

        except Exception as e:
            self.log(f"❌ edit_cell_content: {e}")

    def _handle_existing_entry_edit(self, *, row: int, prefix: str):
        real_idx = self._visual_to_real(row)
        if real_idx is None:
            return

        ok, result, err = self.address_edit_workflow.edit_existing_entry_block(real_idx=real_idx,
                                                                               prefix=prefix,
                                                                               parent=self.table, )
        if not ok:
            if err == "empty_block":
                self.log(f"{prefix}: Пустое редактирование в строке {row + 1} — изменения отменены.")
            elif err != "dialog_cancelled":
                self.log(f"❌ Не удалось обновить {prefix} в строке {row + 1}: {err}")
            return

        if callable(self.reload_callback):
            self.reload_callback()
        else:
            self.display()

    def save_to_json_on_edit(self, item):
        QTimer.singleShot(0, lambda: self._save_item(item))

    # ---- C.temporary new - entry support
    # TODO: Убрать "handle_new_entry" ключевую строку, и заменить отдельным окном "Создать рейс", для удобства создания задачи на ТС
    def handle_new_entry(self, row_idx: int):
        """Сохранение новой записи из ключевой строки"""
        try:
            ts_item = self.table.item(row_idx, 2)
            ka_item = self.table.item(row_idx, 3)
            fio_item = self.table.item(row_idx, 4)

            ts_phone = ts_item.text().strip() if ts_item else ""
            ka = ka_item.text().strip() if ka_item else ""
            fio = fio_item.text().strip() if fio_item else ""

            if not self.new_task_workflow:
                self.log("⚠️ NewTaskWorkflowService не подключён")
                return

            ok, new_task, err = self.new_task_workflow.create_from_buffer(ts_phone=ts_phone,
                                                                          ka=ka,
                                                                          fio=fio,
                                                                          buffer=self._new_entry_buffer, )
            if not ok:
                self.log(f"⚠️ Не удалось создать задачу: {err}")
                return

            self.log(f"✅ Новая запись добавлена (index={new_task.get('index')})")
            self._new_entry_buffer = {}

            if callable(self.reload_callback):
                self.reload_callback()
            else:
                self.display()

        except Exception as e:
            self.log(f"❌ Ошибка в handle_new_entry: {e}")

    def _add_new_entry_row(self):
        """Добавляет в конец таблицы ключевую строку с ➕."""
        extra_row = self.table.rowCount()
        self.table.insertRow(extra_row)

        btn = QPushButton("➕")
        btn.setStyleSheet("color: green; font-weight: bold;")
        btn.clicked.connect(lambda _, idx=extra_row: self.handle_new_entry(idx))
        self.table.setCellWidget(extra_row, 0, btn)

        id_item = QTableWidgetItem("—")
        id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(extra_row, 1, id_item)

        for col in range(2, self.table.columnCount()):
            self._set_editable_cell(extra_row, col, "")

    def _handle_new_entry_edit(self, *, row: int, col: int, prefix: str):
        ok, result, err = self.address_edit_workflow.edit_new_entry_block(prefix=prefix, parent=self.table, )
        if not ok:
            if err not in ("dialog_cancelled", "empty_block"):
                self.log(f"⚠️ Не удалось подготовить {prefix}: {err}")
            return

        data_block = result["data_block"]
        meta = result["meta"]

        self._new_entry_buffer[prefix] = data_block
        if meta.get("Время отправки"):
            self._new_entry_buffer["Время отправки"] = meta["Время отправки"]
        if meta.get("Транзит"):
            self._new_entry_buffer["Транзит"] = meta["Транзит"]

        temp_entry = {prefix: data_block}
        preview_text = self.formatter.field_with_datetime(temp_entry, prefix)

        self.table.blockSignals(True)
        self._set_editable_cell(row, col, preview_text)
        self.table.blockSignals(False)

    # ---- D.facades to child helpers
    def set_row_busy(self, index_key: int, busy: bool):
        self.row_action_controller.set_row_busy(index_key, busy)

    def set_all_rows_busy(self, busy: bool):
        self.row_action_controller.set_all_rows_busy(busy)

    def _set_editable_cell(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

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
