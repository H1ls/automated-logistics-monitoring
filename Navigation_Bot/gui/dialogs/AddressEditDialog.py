import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QLineEdit, QPushButton, QScrollArea, QWidget, QTextEdit
)

from Navigation_Bot.core.datasetArchive import DatasetArchive
from Navigation_Bot.core.processedFlags import StatusEditorWidget, init_processed_flags
from Navigation_Bot.gui.dialogs.sitesDbEditorDialog import SitesDbEditorDialog


class AddressEditDialog(QDialog):
    """Диалог редактирования блоков Погрузка/Выгрузка."""

    def __init__(self, row_data, full_data, prefix, parent=None, disable_save=False, data_context=None, log_func=None):
        super().__init__(parent)
        self.setWindowTitle(f"Редактирование: {prefix}")
        self.resize(1000, 500)

        self.prefix = prefix
        self.row_data = row_data
        self.full_data = full_data
        self.disable_save = disable_save
        self.data_context = data_context
        self.log = log_func or print
        self.sites_db = self._load_sites_db()
        self.entries = []  # список кортежей (container, address_edit, arr_date_edit, arr_time_edit)

        #  ключ для raw_*
        if self.prefix == "Погрузка":
            self.raw_key = "raw_load"
        else:
            self.raw_key = "raw_unload"

        # --- Верхний уровень UI ---
        self.layout = QVBoxLayout(self)

        # scroll для точек
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

        # loads для чекбоксов - только по реальным точкам
        loads = [blk.get(f"{self.prefix} {i + 1}", "") for i, blk in enumerate(points)]

        # processed выравниваем до длины points
        proc = self.row_data.get("processed", []) or []
        proc = (proc + [False] * len(points))[:len(points)]

        self.status_editor = StatusEditorWidget(processed=proc,
                                                loads=loads,
                                                distance=row_data.get("distance", float("inf")))

        # --- raw_* строка ---
        raw_value = (self.row_data.get(self.raw_key) or "").strip()
        self.raw_edit = QTextEdit(raw_value)
        self.raw_edit.setPlaceholderText(self.raw_key)
        self.raw_edit.setFixedHeight(50)

        # --- Комментарий ---
        self.comment_label = QLabel("Комментарий:")
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText(f"{self.prefix} другое / комментарий")
        self.comment_edit.setFixedHeight(60)
        if self._comment_text:
            self.comment_edit.setPlainText(self._comment_text)

        # --- Предзаполнение реальных точек (без комментария) ---
        for i, item in enumerate(points, 1):
            address = item.get(f"{self.prefix} {i}", "")
            date = item.get(f"Дата {i}", "")
            time = item.get(f"Время {i}", "")
            self.add_entry(address, date, time)

        # --- Кнопки ---
        self.btn_add = QPushButton("➕ Добавить точку")
        self.btn_add.clicked.connect(lambda: self.add_entry())

        self.btn_archive = QPushButton("📦 В архив")
        self.btn_archive.clicked.connect(self._archive_sample)

        self.btn_save = QPushButton("✅ Сохранить")
        self.btn_save.clicked.connect(self._accept)

        # --- Сборка layout в нужном порядке ---
        self.layout.addWidget(self.status_editor)  # чекбоксы
        self.layout.addWidget(self.raw_edit)  # RAW строка

        self.layout.addWidget(self.comment_label)  # Комментарий
        self.layout.addWidget(self.comment_edit)

        self.layout.addWidget(self.scroll_area)  # список точек

        # Кнопки
        btns = QHBoxLayout()
        btns.addWidget(self.btn_add)
        btns.addStretch(1)
        btns.addWidget(self.btn_archive)
        btns.addWidget(self.btn_save)
        self.layout.addLayout(btns)

    def open_sites_editor(self, prefill_address: str = "") -> None:
        dlg = SitesDbEditorDialog(parent=self, prefill_address=prefill_address, log_func=self.log)
        dlg.exec()
        self.sites_db = self._load_sites_db()

    # Helpers
    def _load_sites_db(self) -> list[dict]:
        path = Path("LogistX/config") / "sites_db.json"
        try:
            if not path.exists():
                return []
            data = json.loads(path.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
        except Exception as e:
            self.log(f"❌ Ошибка чтения sites_db.json: {e}")
            return []

    def _norm(self, s: str) -> str:
        s = (s or "").lower().replace("ё", "е")
        s = re.sub(r"[^\w\s]", " ", s)  # убрать пунктуацию
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _resolve_site_by_aliases(self, address: str) -> dict | None:
        """
        Возвращает лучший match:
        {"site_id": "...", "geofence": "...", "score": int}
        либо None
        """
        addr_n = self._norm(address)
        if not addr_n or not self.sites_db:
            return None

        best = None
        best_score = 0

        for obj in self.sites_db:
            aliases = obj.get("aliases") or []
            if not isinstance(aliases, list):
                continue

            score = 0
            for a in aliases:
                a_n = self._norm(str(a))
                if a_n and a_n in addr_n:
                    score += 1

            if score > best_score:
                best_score = score
                best = obj

        if best and best_score > 0:
            return {
                "site_id": str(best.get("site_id", "") or ""),
                "geofence": str(best.get("geofence", "") or ""),
                "score": best_score
            }

        return None

    @staticmethod
    def _normalize_date(line_edit: QLineEdit) -> None:
        """Если введён только день - подставляем текущий месяц и год."""
        text = line_edit.text().strip()
        if not text:
            return
        parts = text.split(".")
        now = datetime.now()
        # варианты: "5", "05", "05.__.__"
        try:
            if len(parts) == 1 or (len(parts) == 3 and not parts[1] and not parts[2]):
                day = int(parts[0])
                line_edit.setText(f"{day:02d}.{now.month:02d}.{now.year}")
        except Exception:
            pass

    @staticmethod
    def _normalize_time(line_edit: QLineEdit) -> None:
        """Доводим время до формата HH:MM, добивая нулями."""
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

    def _connect_normalizers(self, dep_date: QLineEdit, dep_time: QLineEdit,
                             arr_date: QLineEdit, arr_time: QLineEdit) -> None:
        dep_date.editingFinished.connect(lambda: self._normalize_date(dep_date))
        arr_date.editingFinished.connect(lambda: self._normalize_date(arr_date))
        dep_time.editingFinished.connect(lambda: self._normalize_time(dep_time))
        arr_time.editingFinished.connect(lambda: self._normalize_time(arr_time))

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

                container._meta = {"Время отправки": full_dt.strftime("%d.%m.%Y %H:%M"),
                                   "Транзит": f"{transit.value()} ч", }

            except Exception as e:
                print(f"[DEBUG] ❌ Ошибка расчёта: {e}")

        btn_calc.clicked.connect(calculate_arrival)

    #       UI для точек
    def add_entry(self, address="", date="", time=""):
        container = QWidget()
        wrapper = QVBoxLayout(container)

        wrapper.setSpacing(8)  # расстояние между строкой 4 и 5
        wrapper.setContentsMargins(0, 0, 0, 0)

        #  Строка 4. Погрузка + Дата выезда + Время + Транзит + Кнопка
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        prefix_label = QLabel(self.prefix)
        tags_label = QLabel("")
        tags_label.setStyleSheet("color: #666;")  # можно убрать/изменить

        # Лейбл "Погрузка" / "Выгрузка" слева
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

        btn_geo = QPushButton("🏷")
        btn_geo.setFixedWidth(30)
        btn_geo.setToolTip("Редактор геозон/складов")
        btn_geo.clicked.connect(lambda: self.open_sites_editor(
            prefill_address=address_input.toPlainText().strip() if 'address_input' in locals() else address.strip()))

        # ред.гео
        top_row.addWidget(btn_geo)

        # слева текст "Погрузка"
        top_row.addWidget(prefix_label)
        top_row.addWidget(tags_label)  # <-- теги сразу рядом

        top_row.addStretch()  # растяжка, чтобы увести дату/время вправо
        top_row.addWidget(QLabel("Дата выезда:"))
        top_row.addWidget(dep_date)
        top_row.addWidget(dep_time)
        top_row.addWidget(QLabel("Транзит:"))
        top_row.addWidget(transit)
        top_row.addWidget(btn_calc)

        # Строка 5. Адрес + Дата прибытия + Время + Удалить
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        address_input = QTextEdit(address)

        def _update_tags_from_address():
            addr = address_input.toPlainText().strip()
            hit = self._resolve_site_by_aliases(addr)

            if hit and hit["geofence"]:
                container._site_id = hit["site_id"]
                container._geo_tags = [hit["geofence"]]
                tags_label.setText(f"  🏷 {hit['geofence']}")
                tags_label.show()
            else:
                container._site_id = ""
                container._geo_tags = []
                tags_label.setText("")
                tags_label.hide()

        tags_label.hide()
        # первичное заполнение (если address уже пришёл)
        _update_tags_from_address()

        # обновление на каждое изменение текста
        address_input.textChanged.connect(_update_tags_from_address)
        address_input.setPlaceholderText("Адрес")
        address_input.setFixedHeight(24)

        # даём адресу «вес» 1, чтобы он растягивался, а даты/кнопка были справа
        bottom_row.addWidget(address_input, 1)

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

        bottom_row.addWidget(arr_date)
        bottom_row.addWidget(arr_time)
        bottom_row.addWidget(btn_delete)

        # нормализация дат/времени
        self._connect_normalizers(dep_date, dep_time, arr_date, arr_time)
        self._connect_calculator(dep_date, dep_time, arr_date, arr_time, transit, container, btn_calc)

        # сборка блока точки
        wrapper.addLayout(top_row)

        wrapper.addLayout(bottom_row)
        wrapper.addStretch(1)

        self.scroll_layout.addWidget(container)
        self.entries.append((container, address_input, arr_date, arr_time))

    def remove_entry(self, widget: QWidget) -> None:
        for i, (container, *_) in enumerate(self.entries):
            if container == widget:
                self.scroll_layout.removeWidget(container)
                container.deleteLater()
                del self.entries[i]
                break

    #  Сохранение / архив
    def _accept(self) -> None:
        """Нажатие на 'Сохранить' внутри диалога."""
        try:
            if hasattr(self, "status_editor"):
                processed = self.status_editor.get_processed()
                self.row_data["processed"] = processed

            if hasattr(self, "raw_edit") and hasattr(self, "raw_key"):
                self.row_data[self.raw_key] = self.raw_edit.toPlainText().strip()

            if not self.disable_save and self.data_context is not None:
                json_data = self.data_context.get()
                row_index = json_data.index(self.row_data) if self.row_data in json_data else None
                if row_index is not None:
                    json_data[row_index] = self.row_data

                # пересоздаём processedFlags только для этой строки
                init_processed_flags([self.row_data], [self.row_data], loads_key=self.prefix)

                self.data_context.save()

            super().accept()
        except Exception as e:
            print(f"[DEBUG] ❌ Ошибка в _accept(): {e}")

    def get_result(self):
        """
        Возвращает:result: список блоков [{prefix 1, Дата 1, Время 1}, ... ({'Комментарий': ...})]
        """
        result = []
        meta_result = {}

        for idx, (container, address_input, date_input, time_input) in enumerate(self.entries, 1):
            address = address_input.toPlainText().strip()
            date = date_input.text().strip()
            time = time_input.text().strip()
            if not address:
                continue
            row = {f"{self.prefix} {idx}": address,
                   f"Дата {idx}": date or "Не указано",
                   f"Время {idx}": time or "Не указано"
                   }
            result.append(row)

            if hasattr(container, "_meta"):
                meta = container._meta
                if meta.get("Время отправки"):
                    meta_result["Время отправки"] = meta["Время отправки"]
                if meta.get("Транзит"):
                    meta_result["Транзит"] = meta["Транзит"]

        # добавляем комментарий отдельным блоком
        comment_val = (self.comment_edit.toPlainText() if hasattr(self, "comment_edit") else "").strip()
        if comment_val:
            result.append({"Комментарий": comment_val})

        return result, meta_result

    def _archive_sample(self):
        """
        Архивируем :{"input": "<raw>",
                     "output": [{"Адрес":".", "Дата":".", "Время":"."}, ...]}"""
        try:
            raw_input = (self.raw_edit.toPlainText().strip()
                         if hasattr(self, "raw_edit")
                         else (self.row_data.get(self.raw_key, "") or "").strip())

            output = []
            for idx, (container, address_input, date_input, time_input) in enumerate(self.entries, 1):
                addr = address_input.toPlainText().strip()
                date = (date_input.text() if hasattr(date_input, "text") else "").strip()
                time = (time_input.text() if hasattr(time_input, "text") else "").strip()
                if not addr:
                    continue
                output.append({"Адрес": addr,
                               "Дата": date,
                               "Время": time,
                               })
            comment_val = (self.comment_edit.toPlainText() if hasattr(self, "comment_edit") else "").strip()
            if comment_val:
                if output:
                    # комментарий в последнюю реальную точку,если там уже есть, аккуратно объединим
                    if "Комментарий" in output[-1] and output[-1]["Комментарий"]:
                        output[-1]["Комментарий"] = f"{output[-1]['Комментарий']}\n{comment_val}"
                    else:
                        output[-1]["Комментарий"] = comment_val
                else:
                    # точек нет — коммент отдельной записью
                    output.append({"Адрес": "", "Дата": "", "Время": "", "Комментарий": comment_val})

            sample = {"input": raw_input,
                      "output": output
                      }

            self.log(f"📦 В архив добавлено: {raw_input[:60]}...")
            DatasetArchive(log_func=self.log).append(sample)
        except Exception as e:
            print(f"❌ Ошибка в _archive_sample: {e}")
