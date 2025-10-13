from functools import partial
from collections import ChainMap
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem, QPushButton, QWidget, QHBoxLayout, QLabel, QCheckBox, QVBoxLayout

from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import INPUT_FILEPATH, ID_FILEPATH
from Navigation_Bot.gui.AddressEditDialog import AddressEditDialog

"""TODO:2._save_item() растёт : Количество if-ов -> Создать словарь стратегий:
                                                    self.field_savers = {"ТС": self._save_ts_and_phone,
                                                                         "id": self._save_id}"""


class TableManager:
    def __init__(self, table_widget, data_context, log_func, on_row_click, on_edit_id_click, gsheet):
        self.data_context = data_context
        self.table = table_widget
        self.log = log_func
        self.on_row_click = on_row_click
        self.on_edit_id_click = on_edit_id_click
        self._new_entry_buffer = {}
        self.gsheet = gsheet

    def display(self, reload_from_file=True):
        if reload_from_file:
            try:
                self.data_context.reload()
            except Exception as e:
                self.log(f"❌ Ошибка при загрузке JSON: {e}")
                json_data = []

        json_data = self.data_context.get()

        try:
            scroll_value = self.table.verticalScrollBar().value()
            selected_row = self.table.currentRow()
        except Exception as e:
            print(f'{e}')

        try:
            self.table.blockSignals(True)  # 🚫 отключаем сигналы
            self.table.setRowCount(0)

            for row_idx, row in enumerate(json_data):
                self.table.insertRow(row_idx)
                # Кнопка ▶ или 🛠
                btn = QPushButton("▶" if row.get("id") else "🛠")
                if not row.get("id"):
                    btn.setStyleSheet("color: red;")
                    btn.clicked.connect(lambda _, idx=row_idx: self.on_edit_id_click(idx))
                else:
                    btn.clicked.connect(lambda _, idx=row_idx: self.on_row_click(idx))
                self.table.setCellWidget(row_idx, 0, btn)

                # ID с кнопкой 🛠
                id_value = str(row.get("id", ""))
                container = QWidget()
                layout = QHBoxLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                label = QLabel(id_value)
                btn_tool = QPushButton("🛠")
                btn_tool.setFixedWidth(30)
                btn_tool.clicked.connect(partial(self.on_edit_id_click, row_idx))
                layout.addWidget(label)
                layout.addWidget(btn_tool)
                layout.addStretch()
                container.setLayout(layout)
                self.table.setCellWidget(row_idx, 1, container)

                ts = row.get("ТС", "")
                phone = row.get("Телефон", "")
                self._set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

                self._set_cell(row_idx, 3, row.get("КА", ""), editable=True)
                self._set_cell(row_idx, 4, self._get_field_with_datetime(row, "Погрузка"))
                # self._set_cell(row_idx, 5, self._get_field_with_datetime(row, "Выгрузка"))
                self._set_unload_cell_with_status(row_idx, row)

                self._set_cell(row_idx, 6, row.get("гео", ""))

                arrival = row.get("Маршрут", {}).get("время прибытия", "—")
                buffer = row.get("Маршрут", {}).get("time_buffer", "—")
                if ":" in buffer:
                    try:
                        h, m = map(int, buffer.split(":"))
                        buffer = f"{h}ч {m}м"
                    except Exception:
                        pass

                self._set_readonly_cell(row_idx, 7, arrival)
                self._set_readonly_cell(row_idx, 8, buffer)

                # Подсветка при поздней погрузке
                pg = row.get("Погрузка", [])
                if pg and isinstance(pg, list) and isinstance(pg[0], dict):
                    date_str = pg[0].get("Дата 1", "")
                    time_str = pg[0].get("Время 1", "")
                    try:
                        if time_str.count(":") == 1:
                            time_str += ":00"
                        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
                        if dt > datetime.now() + timedelta(hours=3):
                            for col in range(self.table.columnCount()):
                                item = self.table.item(row_idx, col)
                                if item:
                                    item.setBackground(QColor(210, 235, 255))
                    except Exception as e:
                        ts = row.get("ТС", "—")
                        self.log(
                            f"[DEBUG] ❗️ Ошибка при анализе ДАТЫ/ВРЕМЕНИ Погрузки у ТС: {ts} (строка {row_idx + 1}):")
                        # print(f"[DEBUG] ❗️ Ошибка при анализе времени Погрузки у ТС: {ts} (строка {row_idx + 1}): {e}")

            self.table.resizeRowsToContents()

            # --- добавляем ключевую строку ---
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

        finally:
            self.table.blockSignals(False)  # ✅ включаем сигналы обратно
            QTimer.singleShot(0, lambda: self._restore_scroll(scroll_value, selected_row))

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

    def _set_unload_cell_with_status(self, row_idx: int, row: dict):
        unloads = row.get("Выгрузка", [])
        processed = row.get("processed", [])

        if len(unloads) <= 1:
            self._set_cell(row_idx, 5, self._get_field_with_datetime(row, "Выгрузка"))
            return

        text_parts = []
        for i, unload in enumerate(unloads):
            prefix = f"Выгрузка {i + 1}"
            address = unload.get(prefix, "")
            date = unload.get(f"Дата {i + 1}", "")
            time = unload.get(f"Время {i + 1}", "")

            checked = processed[i] if i < len(processed) else False
            checkbox = "☑️" if checked else "⬜️"

            part = f"{date} {time}\n{address}  {checkbox}"
            text_parts.append(part.strip())

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
            self.display()

        except Exception as e:
            self.log(f"❌ Ошибка в handle_new_entry: {e}")

    def _extract_row_data(self, row_idx):
        """Собирает dict из ключевой строки таблицы"""
        ts_phone = self.table.item(row_idx, 2).text().strip()
        ka = self.table.item(row_idx, 3).text().strip()
        load = self.table.item(row_idx, 4).text().strip()
        unload = self.table.item(row_idx, 5).text().strip()
        fio = ""

        if not ts_phone:
            return None

        parts = ts_phone.split()
        ts = " ".join(parts[:-1]) if len(parts) > 1 else ts_phone
        phone = parts[-1] if len(parts) > 1 else ""

        return {
            "ТС": ts,
            "Телефон": phone,
            "ФИО": fio if fio else [],
            "КА": ka,
            "Погрузка": [{"Погрузка 1": load}] if load else [],
            "Выгрузка": [{"Выгрузка 1": unload}] if unload else []
        }

    @staticmethod
    def _get_field_with_datetime(row, key):
        if isinstance(row.get(key), list):
            blocks = []
            for i, block in enumerate(row[key], 1):
                date = block.get(f"Дата {i}", "")
                time = block.get(f"Время {i}", "")
                address = block.get(f"{key} {i}", "")
                entry = f"{date} {time}".strip()
                if entry and entry != "Не указано Не указано":
                    blocks.append(entry)
                if address:
                    blocks.append(address)
                if i < len(row[key]):
                    blocks.append("____________________")
            return "\n".join(blocks)
        return ""

    def edit_cell_content(self, row, col):
        col_name = self.table.horizontalHeaderItem(col).text()

        if col_name in ["Погрузка", "Время погрузки"]:
            prefix = "Погрузка"
        elif col_name in ["Выгрузка", "Время выгрузки"]:
            prefix = "Выгрузка"
        else:
            return

        json_data = self.data_context.get()
        # ключевая строка
        if row >= len(json_data):  # ключевая строка
            temp_entry = {"Погрузка": [], "Выгрузка": []}
            dialog = AddressEditDialog(row_data=temp_entry,
                                       full_data=[],
                                       prefix=prefix,
                                       parent=self.table,
                                       disable_save=True,
                                       data_context=self.data_context)
            if dialog.exec():
                data_block, meta = dialog.get_result()
                self._new_entry_buffer[prefix] = data_block
                if meta.get("Время отправки"):
                    self._new_entry_buffer["Время отправки"] = meta["Время отправки"]
                if meta.get("Транзит"):
                    self._new_entry_buffer["Транзит"] = meta["Транзит"]

                # отрисовать в таблице превью (только текст, JSON не трогаем)
                temp_entry[prefix] = data_block
                preview_text = self._get_field_with_datetime(temp_entry, prefix)

                self.table.blockSignals(True)
                self._set_editable_cell(row, col, preview_text)
                self.table.blockSignals(False)
            return

        # обычные строки
        dialog = AddressEditDialog(row_data=self.data_context.get()[row],
                                   full_data=self.data_context.get(),
                                   prefix=prefix,
                                   parent=self.table,
                                   data_context=self.data_context)
        if dialog.exec():
            data_block, meta = dialog.get_result()
            if not data_block:
                self.log(f"{prefix}: Пустое редактирование в строке {row + 1} — изменения отменены.")
                return

            json_data[row][prefix] = data_block
            if meta.get("Время отправки"):
                json_data[row]["Время отправки"] = meta["Время отправки"]
            if meta.get("Транзит"):
                json_data[row]["Транзит"] = meta["Транзит"]

            self.data_context.save()
            self.display()

    def save_to_json_on_edit(self, item):
        QTimer.singleShot(0, lambda: self._save_item(item))

    def _save_item(self, item):
        json_data = self.data_context.get()

        row = item.row()
        col = item.column()
        if row >= len(json_data):
            # это ключевая строка — не сохраняем здесь
            return
        header = self.table.horizontalHeaderItem(col).text()
        value = item.text()
        if header.lower() == "гео":
            header = "гео"
        if header in ["Погрузка", "Выгрузка", "Время погрузки", "Время выгрузки"]:
            return
        if header in ["Время прибытия", "Запас", "Запас времени"]:
            # Эти поля только для отображения — не сохраняем их
            return

        # 🔧 Обработка колонки "ТС" (с телефоном)
        if header == "ТС":
            lines = value.splitlines()
            ts = lines[0] if lines else ""
            phone = lines[1] if len(lines) > 1 else ""

            old_ts = json_data[row].get("ТС", "")
            old_phone = json_data[row].get("Телефон", "")

            if ts == old_ts and phone == old_phone:
                return

            json_data[row]["ТС"] = ts
            json_data[row]["Телефон"] = phone
            self.data_context.save()
            # self.log(f"✏️ Изменено: строка {row + 1}, ТС → {ts}, Телефон → {phone}")
            return

        # Стандартное поведение
        # if header == "id":
        #     try:
        #         value = int(value)
        #     except ValueError:
        #         self.log(f"⚠️ Неверный формат ID в строке {row + 1}")
        #         return
        if header == "id":
            if not value.strip().isdigit():
                self.log(f"⚠️ Неверный ID в строке {row + 1}")
                return
            value = int(value)

        old_value = json_data[row].get(header)

        if old_value == value:
            return

        json_data[row][header] = value
        self.data_context.save()
        # self.log(f"✏️ Изменено: строка {row + 1}, колонка '{header}' → {value}")
