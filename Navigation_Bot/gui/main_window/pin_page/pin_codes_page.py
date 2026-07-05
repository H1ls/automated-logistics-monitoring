from __future__ import annotations

import os
import time
from typing import List, Optional
from PyQt6.QtCore import QStringListModel, Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QGridLayout, QLabel, QLineEdit,
                             QFrame, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy, QCompleter, QScrollArea)
from Navigation_Bot.gui.main_window.pin_page.pin_card_image_resolver import PinCardImageResolver
from Navigation_Bot.gui.main_window.pin_page.pin_codes_store import PinCodesData, PinCodesStore
from Navigation_Bot.core.domain.entities.pin_code import PinRow, normalize_pin_text
from Navigation_Bot.core.logging import noop_log, normalize_log_func
from Navigation_Bot.core.paths import PIN_CARD_IMAGES_DIR
from Navigation_Bot.gui.main_window.pin_page.pin_card_widget import PinCardWidget


class PinCodesPage(QWidget):
    """
    Локальная страница "Пин коды":
    - читает xlsx (Лист 1)
    - строит json-индекс (для быстрой загрузки) + хранит rows
    - автодополнение:
        * по Номер ТС — подстрока (например "49" -> "Н 498..." и "Р 549...")
        * по номеру карты — подстрока (например "3490" -> "3001034900"...)
    """

    def __init__(self, xlsx_path: str, json_path: str, log_func=None, parent: Optional[QWidget] = None, ):
        super().__init__(parent)
        self.xlsx_path = str(xlsx_path)
        self.json_path = str(json_path)
        self.log = normalize_log_func(log_func or noop_log)
        self.store = PinCodesStore(self.xlsx_path, self.json_path, log_func=self.log)
        self.image_resolver = PinCardImageResolver(PIN_CARD_IMAGES_DIR)

        self.rows: List[PinRow] = []
        self._mtime: float = 0.0
        self._idx_by_ts = {}
        self._pins_loaded = False
        self._visible_card_count = 0

        self._build_ui()

        # грузим из json (если есть), иначе — из xlsx
        data = self.store.load_cache()
        if data:
            self._apply_data(data, update_summary=False)

        # автопоиск
        self.in_ts.textChanged.connect(self._on_ts_changed)
        self.in_card.textChanged.connect(self._on_card_changed)

        # всё тяжёлое и таймер — после того, как виджет уже создан в Qt
        QTimer.singleShot(0, self._post_init)

        # авто-обновление xlsx -> rows/json
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_if_needed)
        self._timer.start(60_000)  # раз в минуту

    # ---------------- Data ----------------

    def _apply_data(self, data: PinCodesData, *, update_summary: bool = True):
        self.rows = data.rows
        self._mtime = data.xlsx_mtime
        self._pins_loaded = data.pins_loaded
        self._reindex()
        if update_summary:
            self._update_summary()

    # ---------------- UI ----------------

    def _reindex(self):
        self._idx_by_ts = {}
        for i, r in enumerate(self.rows):
            nts = r.n_ts
            if not nts:
                continue
            self._idx_by_ts.setdefault(nts, []).append(i)

    def _post_init(self):
        # грузим кэш
        data = self.store.load_cache()
        if data:
            self._apply_data(data)

        # если кэша нет или он без PIN — строим из xlsx; PIN держим только в памяти
        if not self.rows or not self._pins_loaded:
            self._rebuild_from_xlsx(force=True)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.setStyleSheet("""
            QFrame#PinPanel {
                background: #ffffff;
                border: 1px solid #d8d8d8;
                border-radius: 6px;
            }
            QLabel#SectionTitle {
                font-weight: 600;
                color: #222222;
            }
            QLabel#MutedText {
                color: #666666;
            }
            QLabel#PinValue {
                font-size: 18px;
                font-weight: 700;
                color: #111111;
            }
            QLabel#CardImageSlot {
                background: #f1f3f5;
                border: 1px dashed #b9c0c7;
                border-radius: 4px;
                color: #7a7f85;
            }
            QLineEdit {
                min-height: 26px;
            }
        """)

        top_panel = QFrame()
        top_panel.setObjectName("PinPanel")
        top_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid = QGridLayout(top_panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        # 1) верх: Номер ТС и Карта + поля ввода
        grid.addWidget(QLabel("Номер ТС"), 0, 0)
        grid.addWidget(QLabel("Карта"), 0, 1)

        self.in_ts = QLineEdit()
        self.in_ts.setPlaceholderText("Вводи часть номера ТС (пример: 49)")
        self._ts_completer_model = QStringListModel(self)
        self._ts_completer = QCompleter(self._ts_completer_model, self)
        self._ts_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._ts_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._ts_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._ts_completer.activated.connect(self.set_vehicle_query)
        self.in_ts.setCompleter(self._ts_completer)

        self.in_card = QLineEdit()
        self.in_card.setPlaceholderText("Вводи часть номера карты (пример: 3490)")

        grid.addWidget(self.in_ts, 1, 0)
        grid.addWidget(self.in_card, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        root.addWidget(top_panel)

        # 2) ниже: найденные карты
        detail_panel = QFrame()
        detail_panel.setObjectName("PinPanel")
        detail_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        out = QVBoxLayout(detail_panel)
        out.setContentsMargins(12, 10, 12, 12)
        out.setSpacing(8)

        detail_header = QHBoxLayout()
        detail_title = QLabel("Найденные карты")
        detail_title.setObjectName("SectionTitle")
        self.card_count_label = QLabel("0")
        self.card_count_label.setObjectName("MutedText")
        detail_header.addWidget(detail_title)
        detail_header.addStretch()
        detail_header.addWidget(self.card_count_label)
        out.addLayout(detail_header)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        self.cards_scroll.setWidget(self.cards_host)
        out.addWidget(self.cards_scroll)

        root.addWidget(detail_panel)

        # кнопка ручного обновления
        btn_row = QHBoxLayout()
        self.summary_label = QLabel("Строк: 0")
        self.summary_label.setObjectName("MutedText")
        btn_row.addWidget(self.summary_label)
        btn_row.addStretch()
        self.btn_refresh = QPushButton("Обновить из XLSX")
        self.btn_refresh.clicked.connect(lambda *_: self._rebuild_from_xlsx(force=True))
        btn_row.addWidget(self.btn_refresh)
        root.addLayout(btn_row)
        self._set_card_rows([])

    # ---------------- Helpers ----------------

    @staticmethod
    def norm(s: str) -> str:
        return normalize_pin_text(s)

    def _set_result(self, row: Optional[PinRow]):
        self._set_card_rows([row] if row else [])

    def _clear_card_rows(self):
        if not hasattr(self, "cards_layout"):
            return

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _make_card_widget(self, row: PinRow) -> QWidget:
        return PinCardWidget(row, image_path=self.image_resolver.image_path_for(row.supplier), parent=self)

    def _set_card_rows(self, rows: list[PinRow]):
        self._clear_card_rows()
        self._visible_card_count = len(rows)

        if not rows:
            empty = QLabel("Введите номер ТС или карты")
            empty.setObjectName("MutedText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(90)
            self.cards_layout.addWidget(empty)
        else:
            for row in rows:
                self.cards_layout.addWidget(self._make_card_widget(row))

        self.cards_layout.addStretch()
        self._set_list_counts()

    def _set_list_counts(self):
        if hasattr(self, "card_count_label"):
            self.card_count_label.setText(str(self._visible_card_count))

    def _update_summary(self):
        if not hasattr(self, "summary_label"):
            return

        vehicles = len(self._idx_by_ts)
        cards = len([r for r in self.rows if r.card])
        if self._mtime:
            updated = time.strftime("%d.%m.%Y %H:%M", time.localtime(self._mtime))
            self.summary_label.setText(f"ТС: {vehicles}  •  карт: {cards}  •  XLSX: {updated}")
        else:
            self.summary_label.setText(f"ТС: {vehicles}  •  карт: {cards}")

    def set_vehicle_query(self, vehicle_number: str) -> None:
        value = str(vehicle_number or "").strip()

        self.in_ts.blockSignals(True)
        self.in_ts.setText(value)
        self.in_ts.blockSignals(False)

        q = self.norm(value)
        self._fill_ts_suggestions(q)

        if q in self._idx_by_ts:
            self._fill_cards_for_exact_ts(q)
        else:
            self._set_card_rows([])

        row = self._find_best_by_ts(q)
        if row and q not in self._idx_by_ts:
            self._set_result(row)
        self.in_ts.setFocus()
        self.in_ts.selectAll()

    # ---------------- Autocomplete ----------------
    def _fill_cards_for_exact_ts(self, nts: str, limit: int = 50):
        if not nts:
            self._set_card_rows([])
            return

        idxs = self._idx_by_ts.get(nts, [])
        self._set_card_rows([self.rows[idx] for idx in idxs[:limit]])

    def _on_ts_changed(self):
        q = self.norm(self.in_ts.text())
        self._fill_ts_suggestions(q)

        #  если есть точное совпадение ТС — покажем все карты по нему
        if q in self._idx_by_ts:
            self._fill_cards_for_exact_ts(q)
        else:
            self._set_card_rows([])

    def _on_card_changed(self):
        q = self.norm(self.in_card.text())
        self._fill_card_suggestions(q)

    def _fill_ts_suggestions(self, q: str):
        if not q:
            self._ts_completer_model.setStringList([])
            return

        hits = self._find_rows_by_ts_substring(q, limit=5)
        suggestions = [self.rows[idx].ts for idx in hits]
        self._ts_completer_model.setStringList(suggestions)
        if suggestions and self.in_ts.hasFocus():
            self._ts_completer.complete()

    def _fill_card_suggestions(self, q: str):
        if not q:
            self._set_card_rows([])
            return

        hits = self._find_rows_by_card_substring(q, limit=5)
        self._set_card_rows([self.rows[idx] for idx in hits])

    def _find_rows_by_ts_substring(self, q: str, limit: int = 5) -> List[int]:
        res: List[int] = []
        seen_ts: set[str] = set()
        for i, r in enumerate(self.rows):
            nts = r.n_ts
            if not nts or nts in seen_ts:
                continue
            if q not in nts:
                continue

            seen_ts.add(nts)
            res.append(i)
            if len(res) >= limit:
                break
        return res

    def _find_rows_by_card_substring(self, q: str, limit: int = 5) -> List[int]:
        res: List[int] = []
        for i, r in enumerate(self.rows):
            if q in r.n_card:
                res.append(i)
                if len(res) >= limit:
                    break
        return res

    def _find_best_by_ts(self, q: str) -> Optional[PinRow]:
        if not q:
            return None
        # 1) точное совпадение
        for r in self.rows:
            if r.n_ts == q:
                return r
        # 2) если это просто часть — берём первый hit
        for r in self.rows:
            if q in r.n_ts:
                return r
        return None

    def _find_best_by_card(self, q: str) -> Optional[PinRow]:
        if not q:
            return None
        for r in self.rows:
            if r.n_card == q:
                return r
        for r in self.rows:
            if q in r.n_card:
                return r
        return None

    # ---------------- XLSX / JSON cache ----------------
    def _refresh_if_needed(self):
        try:
            if not os.path.exists(self.xlsx_path):
                return
            mtime = os.path.getmtime(self.xlsx_path)
            if mtime > self._mtime:
                self._rebuild_from_xlsx(force=True)
        except Exception as e:
            self.log(f"❌ PinCodesPage авто-обновление: {e}")

    def _rebuild_from_xlsx(self, force: bool = False):
        data = self.store.rebuild_from_xlsx(current_mtime=self._mtime, force=force)
        if not data:
            return

        self._apply_data(data)
        self.log(f"✅ Пин-коды: загружено {len(self.rows)} строк из XLSX")
        self._fill_ts_suggestions(self.norm(self.in_ts.text()))
        self._fill_card_suggestions(self.norm(self.in_card.text()))
