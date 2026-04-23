from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QPushButton


class RowActionController:
    """
    Отвечает за:
    - кнопки действий в первой колонке
    - busy state по index_key
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

    def register_button(self, index_key: int | None, btn: QPushButton):
        if index_key is not None:
            self._play_buttons[index_key] = btn

    def set_all_rows_busy(self, busy: bool):
        for btn in list(self._play_buttons.values()):
            if btn:
                btn.setEnabled(not busy)

    def set_row_busy(self, index_key: int, busy: bool):
        btn = self._play_buttons.get(index_key)

        if busy:
            if not btn:
                return
            btn.setEnabled(False)
            self._start_spinner(index_key, btn)
        else:
            self._stop_spinner(index_key)
            if btn:
                #TODO: Когда busy=False, текст кнопки всегда сбрасывается в "▶":
                # если по какой-то причине busy когда-то поставят на строку без id, текст логически уже не совпадёт
                btn.setEnabled(True)
                btn.setText("▶")

    def _start_spinner(self, index_key: int, btn: QPushButton):
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