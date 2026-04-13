from __future__ import annotations

from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.scenarios.NavigationBot import NavigationBot
from Navigation_Bot.bots.webDriverManager import WebDriverManager
from Navigation_Bot.bots.scenarios.ReportsBot import WialonReportsBot


class BrowserSession:
    """
    Отвечает за:
    - lifecycle Selenium driver
    - запуск/перезапуск браузера
    - открытие нужных вкладок
    - создание и хранение bot-объектов
    """

    def __init__(self, logger, browser_rect=None, ui_bridge=None):
        self.log = logger
        self.browser_rect = browser_rect
        self.ui_bridge = ui_bridge

        self.driver_manager = WebDriverManager(log_func=self.log)

        self.browser_opened = False

        self.navibot = None
        self.mapsbot = None
        self.reportsbot = None

    def _uilog(self, msg: str) -> None:
        if self.ui_bridge:
            self.ui_bridge.log.emit(msg)
        else:
            self.log(msg)

    def ensure_ready(self) -> None:
        """
        Готовим браузер и основных ботов:
        - если драйвер умер -> сбрасываем состояние
        - если браузер не открыт -> стартуем
        - если боты не созданы -> создаём
        """
        driver = getattr(self.driver_manager, "driver", None)
        if not driver or not self.driver_manager.is_alive():
            self.driver_manager.stop_browser()

            self.browser_opened = False
            self.navibot = None
            self.mapsbot = None
            self.reportsbot = None

        if not self.browser_opened:
            self.driver_manager.start_browser(self.browser_rect)
            self.driver_manager.login_wialon()
            self.driver_manager.open_yandex_maps()
            self.browser_opened = True
            self._uilog("✅ Драйвер и вкладки готовы.")

        if not self.navibot:
            self.navibot = NavigationBot(self.driver_manager.driver, log_func=self.log)

        if not self.mapsbot:
            self.mapsbot = MapsBot(self.driver_manager, log_func=self.log)

    def ensure_reportsbot(self):
        """
        Ленивая инициализация WialonReportsBot.
        Нужен для LogistX/1C сценариев.
        """
        self.ensure_ready()

        if not self.reportsbot:
            self.reportsbot = WialonReportsBot(self.driver_manager.driver, log_func=self.log)

        return self.reportsbot

    def switch_tab_or_log(self, name: str) -> bool:
        ok = self.driver_manager.switch_to_tab(name)
        if ok:
            return True

        if name == "gps.skyglonass" and self.navibot and hasattr(self.navibot, "_ensure_on_wialon_tab"):
            try:
                if self.navibot._ensure_on_wialon_tab():
                    return True
            except Exception:
                pass

        self.log(f"⛔ Не удалось переключиться на вкладку: {name}")
        return False

    def stop(self) -> None:
        try:
            self.driver_manager.stop_browser()
        finally:
            self.browser_opened = False
            self.navibot = None
            self.mapsbot = None
            self.reportsbot = None