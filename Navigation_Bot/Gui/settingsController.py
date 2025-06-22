from Navigation_Bot.Gui.genericSettingsDialog import GenericSettingsDialog
from Navigation_Bot.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.navigationBot import NavigationBot
from Navigation_Bot.mapsBot import MapsBot


class SettingsController:
    def __init__(self, parent, log_func=None):
        self.parent = parent
        self.log = log_func or print
        self.gsheet = parent.gsheet  # используем уже созданный экземпляр

    def open_wialon_settings(self):
        fields = {
            "search_input_xpath": ("XPath поиска", str),
            "unit_block_xpath": ("XPath блока ТС", str),
            "address_selector": ("CSS адреса", str),
            "copy_button_selector": ("CSS копирования координат", str),
            "speed_selector": ("CSS скорости", str)
        }
        dlg = GenericSettingsDialog(
            parent=self.parent,
            title="Настройки Wialon",
            section_index=1,
            section_key="wialon_selectors",
            custom_key="NEW_SELECTORS",
            default_key="DEFAULT_SELECTORS",
            fields=fields,
            file_path="../config/config.json"
        )
        if dlg.exec():
            self.log("📝 Настройки Wialon сохранены.")
            if hasattr(self.parent, "driver_manager") and hasattr(self.parent.driver_manager, "driver"):
                try:
                    self.parent.navibot = NavigationBot(self.parent.driver_manager.driver, self.log)
                    self.log("🔁 NavigationBot пересоздан")
                except Exception as e:
                    msg = str(e).splitlines()[0]
                    self.log(f"❌ Ошибка при создании NavigationBot: {msg}")
            else:
                self.log("ℹ️ NavigationBot будет создан при старте драйвера")

    def open_yandex_settings(self):
        fields = {
            "route_button": ("CSS кнопка маршрута", str),
            "close_route": ("CSS закрытия маршрута", str),
            "from_input": ("XPath Откуда", str),
            "to_input": ("XPath Куда", str),
            "route_item": ("CSS Результат маршрута", str),
            "route_duration": ("CSS длительности", str),
            "route_distance": ("CSS расстояния", str)
        }
        dlg = GenericSettingsDialog(
            parent=self.parent,
            title="Настройки Я.Карт",
            section_index=2,
            section_key="yandex_selectors",
            custom_key="YANDEX_NEW_SELECTORS",
            default_key="YANDEX_DEFAULT_SELECTORS",
            fields=fields,
            file_path="../config/config.json"
        )
        if dlg.exec():
            self.log("📝 Настройки Я.Карт сохранены.")
            if hasattr(self.parent, "driver_manager") and hasattr(self.parent.driver_manager, "driver"):
                try:
                    self.parent.mapsbot = MapsBot(self.parent.driver_manager.driver, self.log)
                    self.log("🔁 MapsBot пересоздан")
                except Exception as e:
                    msg = str(e).splitlines()[0]
                    self.log(f"❌ Ошибка при создании MapsBot: {msg}")
            else:
                self.log("ℹ️ MapsBot будет создан при старте драйвера")

    def open_google_settings(self):
        fields = {
            "creds_file": ("Путь к creds.json", str),
            "sheet_id": ("ID таблицы", str),
            "worksheet_index": ("Индекс листа", int),
            "column_index": ("Индекс колонки", int),
            "file_path": ("Путь к JSON-файлу", str)
        }

        dlg = GenericSettingsDialog(
            parent=self.parent,
            title="Настройки Google",
            section_index=3,
            section_key="google_config",
            custom_key="custom",
            default_key="default",
            fields=fields,
            file_path="../config/config.json"
        )

        if dlg.exec():
            self.log("📝 Настройки Google сохранены.")
            try:
                self.parent.gsheet = GoogleSheetsManager(log_func=self.log)
                self.log("🔁 GoogleSheetsManager пересоздан")
            except Exception as e:
                self.log(f"❌ Ошибка при создании GoogleSheetsManager: {e}")
