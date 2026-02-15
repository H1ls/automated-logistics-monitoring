from __future__ import annotations
from PyQt6.QtGui import QGuiApplication


class WindowLayoutManager:
    """
    Отвечает за размещение главного окна и вычисление прямоугольника для браузера
    при наличии второго монитора.
    """

    def __init__(self, titlebar_offset: int = 30):
        self.titlebar_offset = titlebar_offset

    def apply_dual_screen_layout(self, widget):
        """
        Если есть второй монитор:
          - widget ставим в верхнюю половину второго монитора
          - возвращаем browser_rect (нижняя половина) для WebDriverManager
        Если второго монитора нет — возвращаем None.
        """
        screens = QGuiApplication.screens()
        if len(screens) < 2:
            return None

        second = screens[1]  # второй экран (index=1)
        geom = second.geometry()

        half_h = geom.height() // 2
        off = self.titlebar_offset

        widget.setGeometry(
            geom.x(),
            geom.y() + off,
            geom.width(),
            half_h - off
        )

        return {
            "x": geom.x(),
            "y": geom.y() + half_h,
            "width": geom.width(),
            "height": geom.height() - half_h,
        }
