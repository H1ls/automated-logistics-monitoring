from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.scenarios.NavigationBot import NavigationBot
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager


class SettingsController:
    def __init__(self, gui):
        self.gui = gui
        self.log = gui.log

    def on_settings_changed(self, sections: set):
        gui = self.gui

        if "google_config" in sections:
            gui.gsheet = GoogleSheetsManager(log_func=self.log)
            self.log("🔁 GoogleSheetsManager пересоздан по новым настройкам")

        driver = getattr(getattr(gui, "processor", None), "driver_manager", None)
        driver = getattr(driver, "driver", None)

        if "wialon_selectors" in sections and driver:
            gui.processor.navibot = NavigationBot(driver, log_func=self.log)
            self.log("🔁 NavigationBot пересоздан")

        if "yandex_selectors" in sections:
            dm = getattr(gui.processor, "driver_manager", None)
            if dm:
                gui.processor.mapsbot = MapsBot(dm, log_func=self.log)
                self.log("🔁 MapsBot пересоздан")
            else:
                self.log("ℹ️ MapsBot обновится при запуске драйвера")

        # Если нужно обновлять селекторы, но драйвер ещё не запущен
        if {"wialon_selectors", "yandex_selectors"} & sections and not driver:
            self.log("ℹ️ Селекторы применятся при старте веб-драйвера")
