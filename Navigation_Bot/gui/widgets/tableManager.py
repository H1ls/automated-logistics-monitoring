from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QTableWidgetItem, QPushButton, QWidget, QHBoxLayout, QLabel)

from Navigation_Bot.gui.dialogs.AddressEditDialog import AddressEditDialog
from Navigation_Bot.gui.dialogs.combinedSettingsDialog import VerticalTextDelegate


class TableManager:
    def __init__(self, table_widget, data_context, log_func, on_row_click, on_edit_id_click, gsheet,
                 reload_callback=None):

        self.data_context = data_context
        self.table = table_widget

        # Делегат для вертикального текста в колонке "КА" (индекс 3)
        self._vertical_delegate = VerticalTextDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._vertical_delegate)

        self.log = log_func
        self.on_row_click = on_row_click
        self.on_edit_id_click = on_edit_id_click
        self._new_entry_buffer = {}
        self.gsheet = gsheet
        self._editable_headers = {"Телефон", "ФИО", "КА", "id"}
        self.after_display = None
        self.view_order = []
        self._real_to_visual = {}
        self.reload_callback = reload_callback
        #
        self._play_buttons = {}  # index_key -> QPushButton
        self._spinners = {}  # index_key -> QTimer
        self._spinner_frame = {}  # index_key -> int

    def set_all_rows_busy(self, busy: bool):
        for k, btn in list(self._play_buttons.items()):
            if not btn:
                continue
            btn.setEnabled(not busy)

    def set_row_busy(self, index_key: int, busy: bool):
        btn = self._play_buttons.get(index_key)

        if busy:
            if not btn:
                return
            btn.setEnabled(False)
            self._start_spinner(index_key, btn)
        else:
            #  даже если кнопки уже нет (перерисовка), спиннер всё равно надо остановить
            self._stop_spinner(index_key)
            if btn:
                btn.setEnabled(True)
                btn.setText("▶")

    def _start_spinner(self, index_key: int, btn):
        if index_key in self._spinners:
            return

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_frame[index_key] = 0

        t = QTimer(btn)
        t.setInterval(120)

        def tick():
            i = self._spinner_frame.get(index_key, 0)
            btn.setText(frames[i % len(frames)])
            self._spinner_frame[index_key] = i + 1

        t.timeout.connect(tick)
        t.start()

        self._spinners[index_key] = t

    def _stop_spinner(self, index_key: int):
        t = self._spinners.pop(index_key, None)
        if t:
            try:
                t.stop()
                t.deleteLater()
            except Exception:
                pass
        self._spinner_frame.pop(index_key, None)

    def _set_editable_cell(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    def _split_points_and_comment(self, blocks: list[dict], prefix: str):
        """Возвращает (points, comment_text). Комментарий не считается точкой"""
        points = []
        comment = ""
        for d in blocks or []:
            if not isinstance(d, dict):
                continue
            # поддерживаем оба варианта Комментарий и <prefix> другое
            if "Комментарий" in d:
                comment = str(d.get("Комментарий", "")).strip()
            elif f"{prefix} другое" in d:
                comment = str(d.get(f"{prefix} другое", "")).strip()
            elif any(k.startswith(f"{prefix} ") for k in d.keys()):
                points.append(d)
        return points, comment

    def _restore_scroll(self, scroll_value, selected_row):
        try:
            self.table.verticalScrollBar().setValue(scroll_value)
            if 0 <= selected_row < self.table.rowCount():
                self.table.selectRow(selected_row)
        except Exception as e:
            self.log(f"❌ Ошибка при восстановлении позиции: {e}")

    def _set_unload_cell_with_status(self, row_idx: int, row: dict):
        unloads_all = row.get("Выгрузка", [])
        points, comment = self._split_points_and_comment(unloads_all, "Выгрузка")
        processed = row.get("processed", [])

        # Если 0/1 точка используем общий рендер перед этим временно подменим список только на точки
        if len(points) <= 1:
            temp_row = dict(row)
            temp_row["Выгрузка"] = points
            base_text = self._get_field_with_datetime(temp_row, "Выгрузка")
            if comment:
                base_text = (base_text + ("\n\nКомментарий:\n" + comment) if base_text else "Комментарий:\n" + comment)
            self._set_cell(row_idx, 5, base_text)
            return

        # Несколько точек, рисуем со статусами + комментарий в конце
        text_parts = []
        for i, unload in enumerate(points, start=1):
            prefix = f"Выгрузка {i}"
            address = unload.get(prefix, "")
            date = unload.get(f"Дата {i}", "")
            time = unload.get(f"Время {i}", "")
            checked = processed[i - 1] if i - 1 < len(processed) else False
            checkbox = "☑️" if checked else "⬜️"
            part = f"{date} {time}\n{address}  {checkbox}"
            text_parts.append(part.strip())

        if comment:
            text_parts.append("")
            text_parts.append("Комментарий:")
            text_parts.append(comment)

        combined = "\n\n".join(text_parts)
        self._set_cell(row_idx, 5, combined, editable=False)

    def _set_cell(self, row, col, value, editable=False):
        item = QTableWidgetItem(value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if not editable:
            item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    def _set_readonly_cell(self, row, col, value):
        item = QTableWidgetItem(str(value))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    def handle_new_entry(self, row_idx):
        """Сохранение новой записи из ключевой строки"""
        try:
            ts_phone = self.table.item(row_idx, 2).text().strip()
            ka = self.table.item(row_idx, 3).text().strip()
            fio = self.table.item(row_idx, 4).text().strip()

            if not ts_phone or "Погрузка" not in self._new_entry_buffer or "Выгрузка" not in self._new_entry_buffer:
                self.log("⚠️ Заполните все поля (ТС, КА, Погрузка, Выгрузка)")
                return

            # разбиваем ТС и телефон
            parts = ts_phone.split()
            ts = " ".join(parts[:-1]) if len(parts) > 1 else ts_phone
            phone = parts[-1] if len(parts) > 1 else ""

            new_entry = {
                "ТС": ts,
                "Телефон": phone,
                "ФИО": fio,
                "КА": ka,
                "Погрузка": self._new_entry_buffer.get("Погрузка", []),
                "Выгрузка": self._new_entry_buffer.get("Выгрузка", [])
            }
            if "Время отправки" in self._new_entry_buffer:
                new_entry["Время отправки"] = self._new_entry_buffer["Время отправки"]
            if "Транзит" in self._new_entry_buffer:
                new_entry["Транзит"] = self._new_entry_buffer["Транзит"]

            # index
            json_data = self.data_context.get()
            last_index = max([x.get("index", 0) for x in json_data], default=0)
            index = last_index + 1
            while not self.gsheet.is_row_empty(index):
                index += 1
            new_entry["index"] = index

            # сохраняем в JSON
            json_data.append(new_entry)
            self.data_context.save()

            # отправляем в Google Sheets
            self.gsheet.upload_new_row(new_entry)
            new_entry["uploaded"] = True
            self.data_context.save()

            self.log(f"✅ Новая запись добавлена (index={index})")
            self._new_entry_buffer = {}  # сбрасываем буфер
            # self.display()
            if callable(self.reload_callback):
                self.reload_callback()
            else:
                self.display()

        except Exception as e:
            self.log(f"❌ Ошибка в handle_new_entry: {e}")

    @staticmethod
    def _get_field_with_datetime(row, key):
        blocks = row.get(key)
        if isinstance(blocks, list):
            points = []
            comment = ""
            for d in blocks:
                if not isinstance(d, dict):
                    continue
                if "Комментарий" in d:
                    comment = str(d.get("Комментарий", "")).strip()
                    continue
                if f"{key} другое" in d:
                    comment = str(d.get(f"{key} другое", "")).strip()
                    continue
                points.append(d)

            lines = []
            for i, block in enumerate(points, 1):
                date = block.get(f"Дата {i}", "")
                time = block.get(f"Время {i}", "")
                address = block.get(f"{key} {i}", "")
                dt = f"{date} {time}".strip()
                if dt and dt != "Не указано Не указано":
                    lines.append(dt)
                if address:
                    lines.append(address)
                if i < len(points):
                    lines.append("____________________")

            if comment:
                if lines:
                    lines.append("")  # пустая строка перед комментом
                lines.append("Комментарий:")
                lines.append(comment)

            return "\n".join(lines)
        return ""

    def edit_cell_content(self, row, col):
        try:
            col_name = self.table.horizontalHeaderItem(col).text()

            if col_name in ["Погрузка", "Время погрузки"]:
                prefix = "Погрузка"
            elif col_name in ["Выгрузка", "Время выгрузки"]:
                prefix = "Выгрузка"
            else:
                return

            json_data = self.data_context.get()

            # ✅ ключевая строка (последняя) — работаем как раньше, без real_idx
            # (т.к. это "виртуальная" строка, её нет в json_data и view_order)
            if row >= len(self.view_order) or row >= self.table.rowCount() - 1:
                temp_entry = {"Погрузка": [], "Выгрузка": []}
                dialog = AddressEditDialog(
                    row_data=temp_entry,
                    full_data=[],
                    prefix=prefix,
                    parent=self.table,
                    disable_save=True,
                    data_context=self.data_context,
                    log_func=self.log
                )

                if dialog.exec():
                    data_block, meta = dialog.get_result()
                    self._new_entry_buffer[prefix] = data_block
                    if meta.get("Время отправки"):
                        self._new_entry_buffer["Время отправки"] = meta["Время отправки"]
                    if meta.get("Транзит"):
                        self._new_entry_buffer["Транзит"] = meta["Транзит"]

                    # отрисовать в таблице превью только текст, JSON не трогаем
                    temp_entry[prefix] = data_block
                    preview_text = self._get_field_with_datetime(temp_entry, prefix)

                    self.table.blockSignals(True)
                    self._set_editable_cell(row, col, preview_text)
                    self.table.blockSignals(False)
                return

            # ✅ обычные строки: visual -> real
            if row < 0 or row >= len(self.view_order):
                return
            real_idx = self.view_order[row]
            if real_idx < 0 or real_idx >= len(json_data):
                return

            dialog = AddressEditDialog(
                row_data=json_data[real_idx],
                full_data=json_data,
                prefix=prefix,
                parent=self.table,
                data_context=self.data_context,
                log_func=self.log
            )

            if dialog.exec():
                data_block, meta = dialog.get_result()
                if not data_block:
                    self.log(f"{prefix}: Пустое редактирование в строке {row + 1} — изменения отменены.")
                    return

                json_data[real_idx][prefix] = data_block
                if meta.get("Время отправки"):
                    json_data[real_idx]["Время отправки"] = meta["Время отправки"]
                if meta.get("Транзит"):
                    json_data[real_idx]["Транзит"] = meta["Транзит"]

                self.data_context.save()
                # self.display(view_order=self.sort_controller.build_view_order())
                if callable(self.reload_callback):
                    self.reload_callback()
                else:
                    self.display()
        except Exception as e:
            self.log(f"❌ edit_cell_content: {e}")

    def save_to_json_on_edit(self, item):
        QTimer.singleShot(0, lambda: self._save_item(item))

    def _save_item(self, item):
        if getattr(self, "_block_item_save", False):
            return

        json_data = self.data_context.get()
        row = item.row()
        col = item.column()
        if row >= len(json_data):
            # это ключевая строка — не сохраняем здесь
            return

        header_item = self.table.horizontalHeaderItem(col)
        if not header_item:
            return
        header = header_item.text()

        # только whitelisted
        if header not in self._editable_headers:
            return

        value = item.text()

        # id — отдельные правила
        if header == "id":
            if not value.strip():
                return
            if not value.strip().isdigit():
                self.log(f"⚠️ Неверный ID в строке {row + 1}")
                return
            value = int(value)

        visual_row = item.row()
        if visual_row < 0 or visual_row >= len(self.view_order):
            return

        real_idx = self.view_order[visual_row]
        if real_idx < 0 or real_idx >= len(json_data):
            return

        old_value = json_data[real_idx].get(header)
        if old_value == value:
            return

        json_data[real_idx][header] = value  # ✅ пишем в реальную строку
        self.data_context.save()

        # self.log(f"✏️ Изменено: строка {row + 1}, колонка '{header}' → {value}")

    def visual_row_by_index_key(self, key):
        return self._index_to_visual.get(key, -1)

    def display(self, reload_from_file=True, view_order=None):
        self._reload_context(reload_from_file)
        json_data = self.data_context.get() or []

        # стопаем все спиннеры перед перерисовкой таблицы (иначе они "висят" между display)
        for t in list(self._spinners.values()):
            try:
                t.stop()
                t.deleteLater()
            except Exception:
                pass
        self._spinners.clear()
        self._spinner_frame.clear()
        # и маппинг кнопок тоже очищаем перед новым рендером
        self._play_buttons.clear()

        if view_order is None:
            view_order = list(range(len(json_data)))
        self.view_order = view_order or list(range(len(json_data)))
        # index(key) -> visual_row
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

    #  Вспомогательные методы для display()
    def _reload_context(self, reload_from_file: bool):
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
        """Отрисовывает все обычные строки таблицы"""
        for visual_row, real_idx in enumerate(view_order):
            if not (0 <= real_idx < len(json_data)):
                continue

            row = json_data[real_idx]
            self.table.insertRow(visual_row)

            # визуальная строка = visual_row
            # индекс данных (куда писать) = real_idx
            self._render_row_actions(visual_row, row, real_idx)
            self._render_row_id_cell(visual_row, row, real_idx)
            self._render_row_main_cells(visual_row, row)
            self._render_row_route_cells(visual_row, row)
            self._highlight_future_load(visual_row, row)

    def _render_row_actions(self, row_idx: int, row: dict, real_idx: int):
        """Кнопка ▶ или 🛠 в первом столбце."""
        btn = QPushButton("▶" if row.get("id") else "🛠")

        #  привязка кнопки к index (ключу строки из json)
        index_key = row.get("index")
        if index_key is not None:
            self._play_buttons[index_key] = btn

        if not row.get("id"):
            btn.setStyleSheet("color: red;")
            btn.clicked.connect(lambda _=False, idx=real_idx: self.on_edit_id_click(idx))
        else:
            btn.clicked.connect(lambda _=False, idx=real_idx: self.on_row_click(idx))

        self.table.setCellWidget(row_idx, 0, btn)

    def _render_row_id_cell(self, row_idx: int, row: dict, real_idx: int):
        """Ячейка id с кнопкой 🛠 внутри"""
        id_value = str(row.get("id", ""))
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(id_value)
        btn_tool = QPushButton("🛠")
        btn_tool.setFixedWidth(30)
        btn_tool.clicked.connect(lambda _=False, idx=real_idx: self.on_edit_id_click(idx))

        layout.addWidget(label)
        layout.addWidget(btn_tool)
        layout.addStretch()
        container.setLayout(layout)

        self.table.setCellWidget(row_idx, 1, container)

    def _render_row_main_cells(self, row_idx: int, row: dict):
        """ТС/Телефон, КА, Погрузка, Выгрузка, гео"""
        ts = row.get("ТС", "")
        phone = row.get("Телефон", "")
        self._set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

        self._set_cell(row_idx, 3, row.get("КА", ""), editable=True)
        self._set_cell(row_idx, 4, self._get_field_with_datetime(row, "Погрузка"))
        self._set_unload_cell_with_status(row_idx, row)  # Выгрузка
        self._set_cell(row_idx, 6, row.get("гео", ""))

    def _render_row_route_cells(self, row_idx: int, row: dict):
        """Время прибытия и запас времени."""
        route = row.get("Маршрут", {}) or {}
        arrival = route.get("время прибытия", "—")
        buffer = route.get("time_buffer", "—")

        if isinstance(buffer, str) and ":" in buffer:
            try:
                h, m = map(int, buffer.split(":"))
                buffer = f"{h}ч {m}м"
            except Exception:
                pass

        self._set_readonly_cell(row_idx, 7, arrival)
        self._set_readonly_cell(row_idx, 8, buffer)

    def _highlight_future_load(self, row_idx: int, row: dict):
        """Подсветка строки, если погрузка сильно в будущем"""
        pg = row.get("Погрузка", [])
        if not (pg and isinstance(pg, list) and isinstance(pg[0], dict)):
            return

        date_str = pg[0].get("Дата 1", "")
        time_str = pg[0].get("Время 1", "")
        try:
            if time_str and time_str.count(":") == 1:
                time_str += ":00"
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            if dt > datetime.now() + timedelta(hours=3):
                for col in range(self.table.columnCount()):
                    item = self.table.item(row_idx, col)
                    if item:
                        item.setBackground(QColor(210, 235, 255))
        except Exception:
            ts = row.get("ТС", "—")
            self.log(
                f"[DEBUG] ❗️ Ошибка при анализе ДАТЫ/ВРЕМЕНИ у ТС: {ts} (строка {row_idx + 1}):"
            )

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
