from __future__ import annotations

from Navigation_Bot.bots.maps_bot import MapsBot
from Navigation_Bot.bots.scenarios.navigation_bot import NavigationBot
from Navigation_Bot.bots.web_driver_manager import WebDriverManager
from Navigation_Bot.bots.scenarios.reports_bot import WialonReportsBot


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
        - если драйвер умер -> перезапуск Chrome
        - если вкладка закрыта -> открываем её в том же Chrome
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
            self.browser_opened = True
            self._uilog("✅ Chrome запущен.")

        # Восстанавливаем только недостающие вкладки (без quit/start).
        self.driver_manager.ensure_required_tabs()

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
        if self.driver_manager.switch_to_tab(name):
            return True

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
