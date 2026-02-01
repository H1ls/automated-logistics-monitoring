from PyQt6.QtCore import QObject, QTimer


class SmoothScrollController(QObject):
    def __init__(self, table, speed=0.18, parent=None):
        super().__init__(parent)
        self.table = table
        self.bar = table.verticalScrollBar()

        self.speed = speed  # 0.1 – супер плавно, 0.2–0.25 – быстрее
        self.target = self.bar.value()
        self.current = self.bar.value()

        self._lock = False

        self.timer = QTimer()
        self.timer.timeout.connect(self._animate_step)
        self.timer.start(10)  # чаще тики → более плавно (10–15 мс)

        # ловим обычный скролл
        self.bar.valueChanged.connect(self._on_user_scroll)

    def _on_user_scroll(self, value: int):
        if self._lock:
            return
        # пользователь дёрнул — считаем это новой целью
        self.current = self.bar.value()
        self.target = value

    def scroll_to(self, value: int):
        """Плавно прокрутить к value (можешь вызывать)."""
        self.target = max(self.bar.minimum(), min(self.bar.maximum(), value))

    def _animate_step(self):
        if abs(self.target - self.current) < 0.5:
            return

        # ease-out интерполяция
        delta = (self.target - self.current) * self.speed
        # защита от очень маленьких шагов (чтоб не "залипало")
        if abs(delta) < 0.1:
            delta = 0.1 if self.target > self.current else -0.1

        self.current += delta

        self._lock = True
        self.bar.setValue(int(self.current))
        self._lock = False
