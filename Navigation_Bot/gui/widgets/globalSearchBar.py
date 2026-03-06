from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QLabel, QAbstractItemView, QLineEdit)
try:
    from PyQt6 import sip
except Exception:
    import sip  # fallback (на всякий)

class GlobalSearchBar(QWidget):
    """Плавающая строка поиска по таблице."""

    def __init__(self, table, log_func=print, parent=None):
        super().__init__(parent)
        self.table = table
        self.log = log_func
        self._hits: list[tuple[int, int]] = []
        self._idx: int = -1

        # для подсветки текущей ячейки
        self._highlight_pos: tuple[int, int] | None = None
        self._highlight_prev_brush = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Поиск...")
        self.counter = QLabel("0 из 0")

        self.btn_prev = QPushButton("↑")
        self.btn_next = QPushButton("↓")
        self.btn_close = QPushButton("✕")

        for b in (self.btn_prev, self.btn_next, self.btn_close):
            b.setFixedWidth(24)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # фокус

        layout.addWidget(self.edit)
        layout.addWidget(self.counter)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_close)

        self.edit.textChanged.connect(self._rebuild_hits)
        self.edit.returnPressed.connect(lambda: self._step(1))
        self.btn_next.clicked.connect(lambda: self._step(1))
        self.btn_prev.clicked.connect(lambda: self._step(-1))
        self.btn_close.clicked.connect(self._close_bar)

    def set_table(self, table):
        # если была подсветка в старой таблице — снимаем
        self._clear_highlight()
        self.table = table
        # пересоберём попадания под новую таблицу
        self._rebuild_hits()

    def _close_bar(self):
        """Закрыть строку поиска и убрать подсветку"""
        self._clear_highlight()
        self.hide()

    def _clear_highlight(self):
        """Снять подсветку с текущей ячейки"""
        if not self._highlight_pos:
            return
        if not getattr(self, "table", None) or sip.isdeleted(self.table):
            self._highlight_pos = None
            self._highlight_prev_brush = None
            return

        row, col = self._highlight_pos
        item = self.table.item(row, col)
        if item:
            if self._highlight_prev_brush is not None:
                item.setBackground(self._highlight_prev_brush)
            else:
                item.setBackground(QColor())  # дефолт

        self._highlight_pos = None
        self._highlight_prev_brush = None

    def start(self):
        """Показать панель и подготовить поиск"""
        self.show()
        self.raise_()
        self.edit.setFocus()
        self.edit.selectAll()
        self._rebuild_hits()

    def set_cols(self, cols: list[int] | None):
        """Задать колонки, по которым ищем. None/[] => искать по всем."""
        if cols:
            self.cols_to_check = list(cols)
        else:
            self.cols_to_check = None
        self._rebuild_hits()

    #  внутренняя логика поиска
    from PyQt6 import sip

    def _rebuild_hits(self):
        try:
            # ✅ защита: table может быть None или sip-deleted
            if not getattr(self, "table", None) or sip.isdeleted(self.table):
                self._hits = []
                self._idx = -1
                self.counter.setText("0 из 0")
                return

            term = self.edit.text().strip().lower()
            self._hits = []
            self._idx = -1

            if not term:
                self._clear_highlight()
                self.counter.setText("0 из 0")
                return

            rows = self.table.rowCount()

            # ✅ локальная переменная, не self.*
            cols_to_check = getattr(self, "cols_to_check", None) or list(range(self.table.columnCount()))
            
            for r in range(rows):
                for c in cols_to_check:
                    item = self.table.item(r, c)
                    if item and term in item.text().lower():
                        self._hits.append((r, c))
                        break

            if self._hits:
                self._idx = 0
                self._select_current()

            self._update_counter()

        except Exception as e:
            self.log(f"Упадал GlobalSearchBar._rebuild_hits {e}")

    def _update_counter(self):
        if not self._hits:
            self.counter.setText("0 из 0")
        else:
            self.counter.setText(f"{self._idx + 1} из {len(self._hits)}")

    def _step(self, delta: int):
        if not self._hits:
            self._rebuild_hits()
            return
        if not self._hits:
            return

        self._idx = (self._idx + delta) % len(self._hits)
        self._select_current()
        self._update_counter()
        # фокус остаётся на edit, потому что _select_current уже делает setFocus

    def _select_current(self):
        if self._idx < 0 or self._idx >= len(self._hits):
            return

        # сначала снимаем старую подсветку
        self._clear_highlight()

        row, col = self._hits[self._idx]
        item = self.table.item(row, col)
        if not item:
            return

        # сохраняем прежний фон и красим текущую ячейку в светло-оранжевый
        self._highlight_prev_brush = item.background()
        item.setBackground(QColor("#ffe5b4"))  # мягкий оранжевый
        self._highlight_pos = (row, col)

        self.table.selectRow(row)
        self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

        # Возвращаем фокус в строку поиска
        self.edit.setFocus()

        # if self.log:
        # self.log(f"🔎 Совпадение {self._idx + 1}/{len(self._hits)} (строка {row + 1})")
