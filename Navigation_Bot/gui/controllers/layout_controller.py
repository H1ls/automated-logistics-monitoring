from __future__ import annotations

from Navigation_Bot.gui.settings.window_layout_manager import WindowLayoutManager, LayoutMode


class LayoutController:
    """
    Управляет layout-режимом окна и позицией браузера.

    Отвечает за:
    - чтение layout-настроек из ui_settings
    - создание WindowLayoutManager
    - вычисление browser_rect
    - переключение режима/монитора
    - перепозиционирование браузера, если он уже открыт
    """

    def __init__(self, gui):
        self.gui = gui
        self._layout_manager: WindowLayoutManager | None = None

    # init
    def setup(self) -> None:
        g = self.gui

        layout_config = g.ui_settings.data.get("layout_mode", {})

        if isinstance(layout_config, str):
            layout_mode_str = layout_config
            monitor_index = 1
        else:
            layout_mode_str = layout_config.get("mode", LayoutMode.VERTICAL_SPLIT.value)
            monitor_str = layout_config.get("monitor", "second")
            monitor_index = 0 if monitor_str == "first" else 1

        self._layout_manager = WindowLayoutManager(
            titlebar_offset=30,
            layout_mode=layout_mode_str,
            monitor_index=monitor_index,
        )

        g.browser_rect = self._layout_manager.apply_dual_screen_layout(g)

    # public api
    def apply_from_settings(self):
        g = self.gui

        layout_config = g.ui_settings.data.get("layout_mode", {})

        if isinstance(layout_config, str):
            mode = layout_config
            monitor_index = 1
        else:
            mode = layout_config.get("mode", "vertical")
            monitor_str = layout_config.get("monitor", "second")
            monitor_index = 0 if monitor_str == "first" else 1

        if self.get_monitor_index() != monitor_index:
            self.switch_monitor(monitor_index)

        if self.get_layout_mode() != mode:
            self.switch_layout_mode(mode)

    def switch_layout_mode(self, mode: LayoutMode | str):
        g = self.gui

        if not self._layout_manager:
            raise ValueError("LayoutController is not initialized")

        self._layout_manager.set_layout_mode(mode)
        g.browser_rect = self._layout_manager.apply_dual_screen_layout(g)

        if hasattr(g, "processor") and g.processor:
            g.processor.browser_rect = g.browser_rect

        if isinstance(mode, LayoutMode):
            mode_str = mode.value
        else:
            mode_str = mode

        current_monitor_str = "first" if self._layout_manager.monitor_index == 0 else "second"

        g.ui_settings.data["layout_mode"] = {"mode": mode_str,
                                             "monitor": current_monitor_str,
                                             }
        g.ui_settings._schedule_save()

        self._reposition_browser_if_open()
        g.log(f"✅ Режим размещения изменен на {mode_str}")

    def switch_monitor(self, monitor_index: int):
        g = self.gui

        if not self._layout_manager:
            raise ValueError("LayoutController is not initialized")

        self._layout_manager.set_monitor_index(monitor_index)
        g.browser_rect = self._layout_manager.apply_dual_screen_layout(g)

        if hasattr(g, "processor") and g.processor:
            g.processor.browser_rect = g.browser_rect

        monitor_str = "first" if monitor_index == 0 else "second"

        if "layout_mode" not in g.ui_settings.data:
            g.ui_settings.data["layout_mode"] = {}
        elif isinstance(g.ui_settings.data["layout_mode"], str):
            mode_str = g.ui_settings.data["layout_mode"]
            g.ui_settings.data["layout_mode"] = {"mode": mode_str,
                                                 "monitor": "second",
                                                 }

        g.ui_settings.data["layout_mode"]["monitor"] = monitor_str
        g.ui_settings._schedule_save()

        self._reposition_browser_if_open()
        g.log(f"✅ Монитор изменен на {monitor_str}")

    def get_layout_mode(self) -> str:
        if not self._layout_manager:
            return LayoutMode.VERTICAL_SPLIT.value
        return self._layout_manager.layout_mode.value

    def get_monitor_index(self) -> int:
        if not self._layout_manager:
            return 1
        return self._layout_manager.monitor_index

    # internals
    def _reposition_browser_if_open(self):
        g = self.gui

        if not g.browser_rect:
            return

        try:
            proc = getattr(g, "processor", None)
            browser_session = getattr(proc, "browser_session", None) if proc else None
            driver_manager = getattr(browser_session, "driver_manager", None) if browser_session else None
            driver = getattr(driver_manager, "driver", None) if driver_manager else None

            if not driver:
                return

            driver.set_window_rect(
                g.browser_rect.get("x", 0),
                g.browser_rect.get("y", 0),
                g.browser_rect.get("width", 1024),
                g.browser_rect.get("height", 768),
            )
        except Exception as e:
            g.log(f"⚠️ Ошибка перепозиционирования браузера: {e}")
