from PyQt6.QtCore import QTimer

from Navigation_Bot.gui.controllers.signals_binder import SignalsBinder


class StartupController:
    def __init__(self, gui):
        self.gui = gui

    def start(self) -> None:
        QTimer.singleShot(0, self._setup_local_pages)

    def _setup_local_pages(self) -> None:
        try:
            self.gui.update_startup_status("Загрузка локальных данных...", "Подготовка локальных страниц")
            self.gui.loading.show("Загрузка локальных данных…", "Подготовка локальных страниц")
            self.gui.local_pages_controller.setup()
        except Exception as e:
            self.gui.log(f"❌ Ошибка startup(local_pages): {e}")
        finally:
            QTimer.singleShot(0, self._setup_managers)

    def _setup_managers(self) -> None:
        try:
            self.gui.update_startup_status("Инициализация сервисов...", "Создание таблицы и контроллеров")
            self.gui.loading.show("Инициализация сервисов…", "Создание таблицы и контроллеров")
            self.gui.init_managers()
        except Exception as e:
            self.gui.log(f"❌ Ошибка startup(managers): {e}")
            self.gui.loading.hide()
            self.gui.finish_startup_splash()
            return
        QTimer.singleShot(0, self._bind_signals)

    def _bind_signals(self) -> None:
        try:
            self.gui.update_startup_status("Привязка сигналов...", "Подготовка событий интерфейса")
            self.gui.loading.show("Привязка сигналов…", "Подготовка событий интерфейса")
            SignalsBinder(self.gui).bind()
        except Exception as e:
            self.gui.log(f"❌ Ошибка startup(signals): {e}")
            self.gui.loading.hide()
            self.gui.finish_startup_splash()
            return
        QTimer.singleShot(0, self._finish)

    def _finish(self) -> None:
        try:
            self.gui.update_startup_status("Готово", "Приложение готово к работе")
            self.gui.loading.show("Готово", "Приложение готово к работе")
        finally:
            self.gui.finish_startup_splash()
            QTimer.singleShot(150, self.gui.loading.hide)
            self.gui.dialog_requests.start()
