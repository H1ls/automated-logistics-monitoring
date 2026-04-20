from __future__ import annotations
from enum import Enum

from PyQt6.QtGui import QGuiApplication


class LayoutMode(Enum):
    """Режимы размещения окон на двух мониторах."""
    VERTICAL_SPLIT = "vertical"  # Navigation сверху, браузер снизу
    HORIZONTAL_SPLIT = "horizontal"  # Браузер слева, Navigation справа


class WindowLayoutManager:
    """
    Отвечает за размещение главного окна NavigationGUI и браузерана выбранном мониторе
    Поддерживает два режима размещения
    """

    def __init__(self, titlebar_offset: int = 30, layout_mode: LayoutMode | str = LayoutMode.VERTICAL_SPLIT,
                 monitor_index: int = 1):
        """
        Args:
            titlebar_offset: Отступ для titlebar (по умолчанию 30px для Windows)
            layout_mode: Режим разделения (VERTICAL_SPLIT или HORIZONTAL_SPLIT)
            monitor_index: Индекс монитора (0 для первого, 1 для второго)
        """
        self.titlebar_offset = titlebar_offset
        self.monitor_index = monitor_index  # 0 = first, 1 = second

        # Нормализуем режим
        if isinstance(layout_mode, str):
            try:
                self.layout_mode = LayoutMode(layout_mode)
            except ValueError:
                self.layout_mode = LayoutMode.VERTICAL_SPLIT
        else:
            self.layout_mode = layout_mode

    def apply_dual_screen_layout(self, widget):
        """
        Применяет режим размещения окна Navigation Manager и возвращает прямоугольник для браузера.
        Если выбранный монитор существует — размещает окна в соответствии с mode.
        Если монитора нет — возвращает None.
        """
        screens = QGuiApplication.screens()
        if len(screens) <= self.monitor_index:
            # Монитор не найден, используем первый доступный параллельно
            if len(screens) < 2:
                return None
            screen = screens[0]  # Fallback на первый экран
        else:
            screen = screens[self.monitor_index]

        geom = screen.geometry()

        if self.layout_mode == LayoutMode.VERTICAL_SPLIT:
            return self._apply_vertical_split(widget, geom)
        elif self.layout_mode == LayoutMode.HORIZONTAL_SPLIT:
            return self._apply_horizontal_split(widget, geom)
        else:
            # Fallback на вертикальное разделение
            return self._apply_vertical_split(widget, geom)

    def _apply_vertical_split(self, widget, screen_geom):
        """
        Разделяет экран по вертикали (пополам по высоте):
        - Верхняя половина (с offset): Navigation Manager
        - Нижняя половина: браузер
        """
        half_h = screen_geom.height() // 2
        off = self.titlebar_offset

        # Navigation Manager в верхней половине
        widget.setGeometry(screen_geom.x(),
                           screen_geom.y() + off,
                           screen_geom.width(),
                           half_h - off)

        # Браузер в нижней половине
        return {"x": screen_geom.x(),
                "y": screen_geom.y() + half_h,
                "width": screen_geom.width(),
                "height": screen_geom.height() - half_h,
                }

    def _apply_horizontal_split(self, widget, screen_geom):
        """
        Разделяет экран по горизонтали (пополам по ширине):
        - Левая половина: браузер
        - Правая половина: Navigation Manager
        """
        half_w = screen_geom.width() // 2
        off = self.titlebar_offset

        # Navigation Manager в правой половине
        widget.setGeometry(screen_geom.x() + half_w,
                           screen_geom.y() + off,
                           half_w,
                           screen_geom.height() - off)

        # Браузер в левой половине
        return {"x": screen_geom.x(),
                "y": screen_geom.y(),
                "width": half_w,
                "height": screen_geom.height(),}

    def set_layout_mode(self, mode: LayoutMode | str):
        """Изменить режим размещения в runtime."""
        if isinstance(mode, str):
            try:
                self.layout_mode = LayoutMode(mode)
            except ValueError:
                raise ValueError(f"Неизвестный режим: {mode}")
        else:
            self.layout_mode = mode

    def set_monitor_index(self, index: int):
        """ Изменить индекс монитора в runtime.
            Args: index: 0 = первый монитор, 1 = второй монитор, и т.д."""
        screens = QGuiApplication.screens()
        if index >= len(screens):
            raise ValueError(f"Монитор {index} не найден (всего мониторов: {len(screens)})")
        self.monitor_index = index

    # def get_monitor_index(self) -> int:
    #     """Получить текущий индекс монитора."""
    #     return self.monitor_index

    # def get_layout_mode(self) -> LayoutMode:
    #     """Получить текущий режим размещения."""
    #     return self.layout_mode
