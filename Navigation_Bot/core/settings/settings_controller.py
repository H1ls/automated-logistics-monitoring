from __future__ import annotations

from Navigation_Bot.core.json_store import JsonStore
from Navigation_Bot.core.paths import CONFIG_JSON


class SettingsController:
    """
    Оркестратор изменений настроек.

    Что делает:
    - при смене google_config пересоздаёт GoogleSheetsManager
      и обновляет все зависимости, которые на него ссылаются;
    - при смене selenium-селекторов инвалидирует bot-объекты в BrowserSession,
      чтобы они пересоздались уже с новыми настройками;
    - при смене layout_mode применяет новый монитор/режим размещения.
    """

    def __init__(self, gui):
        self.gui = gui
        self.log = gui.log

    # --- helpers
    def _get_processor(self):
        return getattr(self.gui, "processor", None)

    def _get_browser_session(self):
        processor = self._get_processor()
        return getattr(processor, "browser_session", None) if processor else None

    def _get_driver(self):
        browser_session = self._get_browser_session()
        if not browser_session:
            return None

        driver_manager = getattr(browser_session, "driver_manager", None)
        if not driver_manager:
            return None

        driver = getattr(driver_manager, "driver", None)
        if not driver:
            return None

        try:
            _ = driver.current_url
            return driver
        except Exception:
            return None


    # --- google config
    def _handle_google_config_changed(self):
        gui = self.gui

        try:
            gsheet = getattr(gui, "gsheet", None)
            if not gsheet:
                self.log("⚠️ GoogleSheetsManager не инициализирован")
                return

            self.log("⏳ Применяю настройки Google Sheets…")
            gui.loading.show("Применяю настройки Google Sheets…", "Перечитываю конфигурацию и листы")

            # Перечитать config.json и заново подключиться к Google
            gsheet.load_settings()

            self.log("🔁 GoogleSheetsManager обновлён по новым настройкам")

            # Пересобрать нижние вкладки листов
            if getattr(gui, "sheet_tabs_controller", None):
                gui.sheet_tabs_controller.build()

                # Попробовать восстановить сохранённую/активную вкладку
                activated = gui.sheet_tabs_controller.activate_saved_tab()
                if activated:
                    self.log("✅ Настройки Google Sheets применены")
                    gui.loading.hide()
                    return

            # fallback: если вкладки не активировались
            if getattr(gui, "task_repository", None):
                gui.task_repository.set_source_key(gui._get_sheet_source_key(), reload=False)

            gui.reload_and_show()
            self.log("✅ Настройки Google Sheets применены")

        except Exception as e:
            self.log(f"❌ Ошибка обновления google_config: {e}")
        finally:
            try:
                gui.loading.hide()
            except Exception:
                pass

    # ---selenium selectors / bots
    def _invalidate_browser_bots(self, sections: set[str]):
        """
        Инвалидирует bot-объекты внутри BrowserSession.
        Мы не лезем в старую структуру processor.navibot/mapsbot,
        а работаем с актуальным местом их жизни.
        """
        browser_session = self._get_browser_session()
        driver = self._get_driver()

        if not browser_session:
            if {"wialon_selectors", "yandex_selectors", "reports_selectors"} & sections:
                self.log("ℹ️ BrowserSession ещё не создан — селекторы применятся при следующем запуске.")
            return

        changed_any = False

        if "wialon_selectors" in sections:
            browser_session.navibot = None
            changed_any = True
            if driver:
                self.log("🔁 NavigationBot будет пересоздан с новыми селекторами")
            else:
                self.log("ℹ️ Wialon-селекторы применятся при старте веб-драйвера")

        if "yandex_selectors" in sections:
            browser_session.mapsbot = None
            changed_any = True
            if driver:
                self.log("🔁 MapsBot будет пересоздан с новыми селекторами")
            else:
                self.log("ℹ️ Yandex-селекторы применятся при старте веб-драйвера")

        if "reports_selectors" in sections:
            browser_session.reportsbot = None
            changed_any = True
            if driver:
                self.log("🔁 WialonReportsBot будет пересоздан с новыми селекторами")
            else:
                self.log("ℹ️ Reports-селекторы применятся при старте веб-драйвера")

            # OneCBot внутри LogistxRaceService кэширует reportsbot-зависимость, поэтому его тоже нужно сбросить
            processor = self._get_processor()
            logistx_service = getattr(processor, "logistx_race_service", None) if processor else None
            if logistx_service:
                logistx_service.onec_bot = None
                self.log("🔁 OneCBot будет пересоздан из-за обновления ReportsBot")

        if not changed_any:
            return

    # --- layout
    def _handle_layout_changed(self):
        gui = self.gui

        try:
            controller = getattr(gui, "layout_controller", None)
            if not controller:
                self.log("⚠️ LayoutController не инициализирован")
                return

            controller.apply_from_settings()

        except Exception as e:
            self.log(f"❌ Ошибка смены режима размещения: {e}")

    def apply_processing_settings(self):
        processor = self._get_processor()
        if not processor:
            return

        settings = JsonStore.get_selectors("processing", CONFIG_JSON)
        timeout_seconds = settings.get("timeout_seconds", processor.DEFAULT_TIMEOUT_SECONDS)
        debug_mode = settings.get("debug_mode", processor.DEFAULT_DEBUG_MODE)
        processor.set_timeout_seconds(timeout_seconds)
        processor.set_debug_mode(debug_mode)

    # --- public
    def on_settings_changed(self, sections: set):
        sections = set(sections or [])
        if not sections:
            return

        # 1. Сначала лёгкие локальные изменения
        if {"wialon_selectors", "yandex_selectors", "reports_selectors"} & sections:
            self._invalidate_browser_bots(sections)

        if "layout_mode" in sections:
            self._handle_layout_changed()

        if "processing" in sections:
            self.apply_processing_settings()

        # 2. Тяжёлое переподключение к Google — только если реально меняли google_config
        if "google_config" in sections:
            self._handle_google_config_changed()
