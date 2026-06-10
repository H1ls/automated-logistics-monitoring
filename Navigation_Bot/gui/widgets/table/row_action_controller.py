from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QPushButton


class RowActionController:
    """
    Отвечает за:
    - кнопки действий в первой колонке
    - busy state по row_identity
    - спиннер во время обработки строки
    """

    def __init__(self):
        self._play_buttons: dict[int, QPushButton] = {}
        self._spinners: dict[int, QTimer] = {}
        self._spinner_frame: dict[int, int] = {}

    def clear(self):
        for t in list(self._spinners.values()):
            try:
                t.stop()
                t.deleteLater()
            except Exception:
                pass
        self._spinners.clear()
        self._spinner_frame.clear()
        self._play_buttons.clear()

    def register_button(self, row_identity: int | None, btn: QPushButton):
        if row_identity is not None:
            self._play_buttons[row_identity] = btn

    def set_all_rows_busy(self, busy: bool):
        for btn in list(self._play_buttons.values()):
            if btn:
                btn.setEnabled(not busy)

    def set_row_busy(self, row_identity: int, busy: bool):
        btn = self._play_buttons.get(row_identity)

        if busy:
            if not btn:
                return
            btn.setEnabled(False)
            self._start_spinner(row_identity, btn)
        else:
            self._stop_spinner(row_identity)
            if btn:
                #TODO: Когда busy=False, текст кнопки всегда сбрасывается в "▶":
                # если по какой-то причине busy когда-то поставят на строку без id, текст логически уже не совпадёт
                btn.setEnabled(True)
                btn.setText("▶")

    def _start_spinner(self, row_identity: int, btn: QPushButton):
        if row_identity in self._spinners:
            return

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_frame[row_identity] = 0

        t = QTimer(btn)
        t.setInterval(120)

        def tick():
            i = self._spinner_frame.get(row_identity, 0)
            btn.setText(frames[i % len(frames)])
            self._spinner_frame[row_identity] = i + 1

        t.timeout.connect(tick)
        t.start()
        self._spinners[row_identity] = t

    def _stop_spinner(self, row_identity: int):
        t = self._spinners.pop(row_identity, None)
        if t:
            try:
                t.stop()
                t.deleteLater()
            except Exception:
                pass
        self._spinner_frame.pop(row_identity, None)
