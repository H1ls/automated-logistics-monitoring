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

        # Обработка изменения режима размещения окон
        if "layout_mode" in sections:
            # Используем gui.ui_settings, который уже содержит обновленные данные
            layout_config = gui.ui_settings.data.get("layout_mode", {})
            
            # Поддерживаем оба формата: строка (legacy) и объект (новый)
            if isinstance(layout_config, str):
                mode = layout_config
                monitor_index = 1  # По умолчанию второй монитор
            else:
                mode = layout_config.get("mode", "vertical")
                # Преобразуем монитор из строки в индекс
                monitor_str = layout_config.get("monitor", "second")
                monitor_index = 0 if monitor_str == "first" else 1
            
            try:
                # Если монитор изменился, применяем его первым (он влияет на координаты браузера)
                if gui.get_monitor_index() != monitor_index:
                    gui.switch_monitor(monitor_index)
                    monitor_name = "первый" if monitor_index == 0 else "второй"
                    self.log(f"✅ Монитор изменен на: {monitor_name}")
                
                # Применяем режим размещения
                gui.switch_layout_mode(mode)
                mode_name = "Горизонтальный" if mode == "horizontal" else "Вертикальный"
                self.log(f"✅ Режим размещения: '{mode_name}'")
            except Exception as e:
                self.log(f"❌ Ошибка смены режима размещения: {e}")

        # Если нужно обновлять селекторы, но драйвер ещё не запущен
        if {"wialon_selectors", "yandex_selectors"} & sections and not driver:
            self.log("ℹ️ Селекторы применятся при старте веб-драйвера")