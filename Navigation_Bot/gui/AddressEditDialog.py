from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
                             QLineEdit, QPushButton, QScrollArea, QWidget, QTextEdit)

from datetime import datetime, timedelta

from Navigation_Bot.core.datasetArchive import DatasetArchive
from Navigation_Bot.core.processedFlags import StatusEditorWidget, init_processed_flags


class AddressEditDialog(QDialog):
    """Диалог редактирования блоков Погрузка/Выгрузка."""

    def __init__(self, row_data, full_data, prefix, parent=None, disable_save=False, data_context=None):
        super().__init__(parent)
        self.setWindowTitle(f"Редактирование: {prefix}")
        self.resize(1000, 500)

        self.prefix = prefix
        self.row_data = row_data
        self.full_data = full_data
        self.disable_save = disable_save
        self.data_context = data_context

        self.entries = []  # список кортежей (container, address_edit, arr_date_edit, arr_time_edit)

        # --- Верхний уровень UI ---
        self.layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_area.setWidget(self.scroll_widget)

        # --- отделяем реальные точки от комментария ---
        all_blocks = self.row_data.get(self.prefix, []) or []

        points = []
        self._comment_text = ""
        for d in all_blocks:
            if isinstance(d, dict) and any(k.startswith(f"{self.prefix} ") for k in d.keys()):
                points.append(d)
            elif isinstance(d, dict) and ("Комментарий" in d or f"{self.prefix} другое" in d):
                self._comment_text = d.get("Комментарий", d.get(f"{self.prefix} другое", "")) or ""

        # loads для чекбоксов — только по реальным точкам
        loads = [blk.get(f"{self.prefix} {i + 1}", "") for i, blk in enumerate(points)]

        # processed выравниваем до длины points (без комментария)
        proc = self.row_data.get("processed", []) or []
        proc = (proc + [False] * len(points))[:len(points)]

        self.status_editor = StatusEditorWidget(
            processed=proc,
            loads=loads,
            distance=row_data.get("distance", float("inf"))
        )

        # Предзаполнение реальных точек (без комментария)
        for i, item in enumerate(points, 1):
            address = item.get(f"{self.prefix} {i}", "")
            date = item.get(f"Дата {i}", "")
            time = item.get(f"Время {i}", "")
            self.add_entry(address, date, time)

        self.btn_archive = QPushButton("📦 В архив")
        self.btn_archive.clicked.connect(self._archive_sample)

        self.btn_add = QPushButton("➕ Добавить точку")
        self.btn_add.clicked.connect(lambda: self.add_entry())
        self.btn_save = QPushButton("✅ Сохранить")
        self.btn_save.clicked.connect(self._accept)

        self.comment_label = QLabel("Комментарий:")
        self.comment_edit = QTextEdit(self._comment_text)
        self.comment_edit.setFixedHeight(60)

        # Сборка
        self.layout.addWidget(self.comment_label)
        self.layout.addWidget(self.comment_edit)
        self.layout.addWidget(self.status_editor)
        self.layout.addWidget(self.scroll_area)
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_archive)
        self.layout.addWidget(self.btn_save)

    # ---------- Публичные действия ----------
    def add_entry(self, address: str = "", date: str = "", time: str = "") -> None:
        """Добавляет один блок редактирования точки (верх/низ), подключает обработчики."""
        container = QWidget()
        wrapper = QVBoxLayout(container)

        # Верхняя строка (дата/время выезда + транзит + калькулятор)
        top_row, dep_date, dep_time, transit, btn_calc = self._create_departure_row()

        # Нижняя строка (адрес + дата/время прибытия + удалить)
        bottom_row, address_edit, arr_date, arr_time = self._create_arrival_row(
            address=address, date=date, time=time, container=container
        )

        # Обработчики нормализации даты/времени
        self._connect_normalizers(dep_date, arr_date, dep_time, arr_time)

        # Обработчик кнопки-калькулятора
        self._connect_calculator(dep_date, dep_time, arr_date, arr_time, transit, container, btn_calc)

        # Вёрстка
        wrapper.addLayout(top_row)
        wrapper.addLayout(bottom_row)
        self.scroll_layout.addWidget(container)
        self.entries.append((container, address_edit, arr_date, arr_time))

    def remove_entry(self, widget: QWidget) -> None:
        """Удаляет один блок точки из UI и self.entries."""
        for i, (container, *_rest) in enumerate(self.entries):
            if container == widget:
                self.scroll_layout.removeWidget(container)
                container.deleteLater()
                del self.entries[i]
                break

    def get_result(self):
        """Возвращает (result_list, meta_dict) по всем точкам."""
        result = []
        meta_result = {}

        for idx, (container, address_input, date_input, time_input) in enumerate(self.entries, 1):
            address = address_input.toPlainText().strip()
            date = date_input.text().strip()
            time = time_input.text().strip()
            if not address:
                continue

            row = {
                f"{self.prefix} {idx}": address,
                f"Дата {idx}": date or "Не указано",
                f"Время {idx}": time or "Не указано",
            }
            result.append(row)

            # Доп. метаданные, если были расчёты
            if hasattr(container, "_meta"):
                meta = container._meta
                if meta.get("Время отправки"):
                    meta_result["Время отправки"] = meta["Время отправки"]
                if meta.get("Транзит"):
                    meta_result["Транзит"] = meta["Транзит"]
        # комментарий всегда в конце
        comment_val = (self.comment_edit.toPlainText() if hasattr(self, "comment_edit") else "").strip()
        if comment_val:
            result.append({"Комментарий": comment_val})

        return result, meta_result

    # ---------- Внутренняя логика ----------
    def _accept(self) -> None:
        """Сохраняет processed и текущую строку через data_context, без полной перезаписи файла."""
        try:
            processed = self.status_editor.get_processed()
            self.row_data["processed"] = processed

            if not self.disable_save and self.data_context is not None:
                json_data = self.data_context.get()
                if self.row_data in json_data:
                    idx = json_data.index(self.row_data)
                    json_data[idx] = self.row_data

                # пересоздаём processedFlags только для этой строки
                init_processed_flags([self.row_data], [self.row_data], loads_key=self.prefix)

                self.data_context.save()

            self.accept()
        except Exception as e:
            print(f"[DEBUG] ❌ Ошибка в accept(): {e}")

    # ---------- Создание строк ----------
    def _create_departure_row(self):
        """Возвращает (layout, dep_date, dep_time, transit, btn_calc)."""
        row = QHBoxLayout()

        dep_date = QLineEdit()
        dep_date.setInputMask("00.00.0000")
        dep_date.setPlaceholderText("дд.мм.гггг")
        dep_date.setFixedWidth(80)

        dep_time = QLineEdit()
        dep_time.setInputMask("00:00")
        dep_time.setPlaceholderText("чч:мм")
        dep_time.setFixedWidth(60)

        transit = QSpinBox()
        transit.setRange(0, 999)
        transit.setSuffix(" ч")

        btn_calc = QPushButton("🧮")
        btn_calc.setFixedWidth(30)

        row.addWidget(QLabel("Дата выезда:"))
        row.addWidget(dep_date)
        row.addWidget(dep_time)
        row.addWidget(QLabel("Транзит:"))
        row.addWidget(transit)
        row.addWidget(btn_calc)
        row.addStretch()

        return row, dep_date, dep_time, transit, btn_calc

    def _create_arrival_row(self, address: str, date: str, time: str, container: QWidget):
        """Возвращает (layout, address_edit, arr_date, arr_time) и кнопка удаления уже подключена."""
        row = QHBoxLayout()

        label = QLabel(self.prefix)

        address_edit = QTextEdit(address)
        address_edit.setPlaceholderText("Адрес")
        address_edit.setFixedHeight(60)
        address_edit.setMinimumWidth(600)

        arr_date = QLineEdit()
        arr_date.setInputMask("00.00.0000")
        arr_date.setPlaceholderText("дд.мм.гггг")
        arr_date.setFixedWidth(80)
        if date:
            arr_date.setText(date)

        arr_time = QLineEdit()
        arr_time.setInputMask("00:00")
        arr_time.setPlaceholderText("чч:мм")
        arr_time.setFixedWidth(60)
        arr_time.setText(time[:5] if time else "")

        btn_delete = QPushButton("🗑️")
        btn_delete.setFixedWidth(30)
        btn_delete.clicked.connect(lambda: self.remove_entry(container))

        row.addWidget(label)
        row.addWidget(address_edit)
        row.addWidget(arr_date)
        row.addWidget(arr_time)
        row.addWidget(btn_delete)

        return row, address_edit, arr_date, arr_time

    # ---------- Обработчики ----------
    def _connect_normalizers(self, dep_date: QLineEdit, arr_date: QLineEdit,
                             dep_time: QLineEdit, arr_time: QLineEdit) -> None:
        """Подключает обработчики нормализации даты/времени на loss of focus."""

        def normalize_date(line_edit: QLineEdit):
            text = line_edit.text().strip()
            if not text:
                return
            parts = text.split(".")
            now = datetime.now()
            # если введён только день — подставим текущие месяц и год
            if len(parts) == 1 or (len(parts) == 3 and not parts[1] and not parts[2]):
                try:
                    day = int(parts[0])
                    line_edit.setText(f"{day:02d}.{now.month:02d}.{now.year}")
                except Exception:
                    pass

        def normalize_time(line_edit: QLineEdit):
            text = line_edit.text().strip().replace("_", "")
            if not text:
                return
            try:
                parts = text.split(":")
                if len(parts) == 1:
                    h = int(parts[0] or 0)
                    m = 0
                else:
                    h = int(parts[0] or 0)
                    m = int(parts[1] or 0)
                line_edit.setText(f"{h:02d}:{m:02d}")
            except Exception:
                pass

        dep_date.editingFinished.connect(lambda: normalize_date(dep_date))
        arr_date.editingFinished.connect(lambda: normalize_date(arr_date))
        dep_time.editingFinished.connect(lambda: normalize_time(dep_time))
        arr_time.editingFinished.connect(lambda: normalize_time(arr_time))

    def _connect_calculator(self, dep_date: QLineEdit, dep_time: QLineEdit,
                            arr_date: QLineEdit, arr_time: QLineEdit,
                            transit: QSpinBox, container: QWidget, btn_calc: QPushButton) -> None:

        """Подключает логику кнопки-калькулятора."""

        def calculate_arrival():
            try:
                dep_dt = datetime.strptime(dep_date.text().strip(), "%d.%m.%Y")
                dep_tm = datetime.strptime(dep_time.text().strip(), "%H:%M").time()
                full_dt = datetime.combine(dep_dt.date(), dep_tm)
                if transit.value() <= 0:
                    return
                arrival_dt = full_dt + timedelta(hours=transit.value())

                arr_date.setText(arrival_dt.strftime("%d.%m.%Y"))
                arr_time.setText(arrival_dt.strftime("%H:%M"))

                container._meta = {
                    "Время отправки": full_dt.strftime("%d.%m.%Y %H:%M"),
                    "Транзит": f"{transit.value()} ч",
                }
            except Exception as e:
                print(f"[DEBUG] ❌ Ошибка расчёта: {e}")

        btn_calc.clicked.connect(calculate_arrival)

    def _archive_sample(self, prefix: str):
        """Архивируем минимально:{"input": "<raw>", "output": [{"Адрес":"...", "Дата":"...", "Время":"..."}, ...]}"""
        try:
            if self.prefix == "Погрузка":
                raw_key = "raw_load"
            else:
                raw_key = "raw_unload"

            raw_input = self.row_data.get(raw_key, "").strip()

            output = []
            for idx, (container, address_input, date_input, time_input) in enumerate(self.entries, 1):
                addr = address_input.toPlainText().strip()
                date = (date_input.text() if hasattr(date_input, "text") else "").strip()
                time = (time_input.text() if hasattr(time_input, "text") else "").strip()
                if not addr:
                    continue
                output.append({
                    "Адрес": addr,
                    "Дата": date,
                    "Время": time,
                })

            # comment_val = (self.comment_edit.toPlainText() if hasattr(self, "comment_edit") else "").strip()
            # if comment_val:
            #     if output:
            #         # комментарий в последнюю реальную точку
            #         # если там уже есть "Комментарий", аккуратно объединим
            #         if "Комментарий" in output[-1] and output[-1]["Комментарий"]:
            #             output[-1]["Комментарий"] = f"{output[-1]['Комментарий']}\n{comment_val}"
            #         else:
            #             output[-1]["Комментарий"] = comment_val
            #     else:
            #         # точек нет — коммент отдельной записью
            #         output.append({"Адрес": "", "Дата": "", "Время": "", "Комментарий": comment_val})

            sample = {
                "input": raw_input,
                "output": output
            }

            DatasetArchive(log_func=self.log if hasattr(self, "log") else print).append(sample)
        except Exception as e:
            (self.log if hasattr(self, "log") else print)(f"❌ Ошибка в _archive_sample: {e}")
