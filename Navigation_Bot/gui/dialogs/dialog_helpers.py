"""Общие приёмы разметки для диалогов: ряды кнопок без дублирования QHBoxLayout."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtWidgets import QHBoxLayout, QWidget


def button_row_trailing(*buttons: QWidget) -> QHBoxLayout:
    """[stretch] · кнопки слева направо (типично «Сохранить», «Отмена»)."""
    row = QHBoxLayout()
    row.addStretch(1)
    for b in buttons:
        row.addWidget(b)
    return row


def button_row_leading(*widgets: QWidget) -> QHBoxLayout:
    """Виджеты слева, затем stretch (вся группа прижата влево)."""
    row = QHBoxLayout()
    for w in widgets:
        row.addWidget(w)
    row.addStretch(1)
    return row


def button_row_split(left: Sequence[QWidget], right: Sequence[QWidget]) -> QHBoxLayout:
    """Группа слева, stretch, группа справа (панель действий + основные кнопки)."""
    row = QHBoxLayout()
    for w in left:
        row.addWidget(w)
    row.addStretch(1)
    for w in right:
        row.addWidget(w)
    return row
