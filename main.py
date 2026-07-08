import os
import sys
import faulthandler

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from Navigation_Bot.core.database_config import DatabaseConfig
from Navigation_Bot.core.infrastructure.api.api_client import NavigationApiClient, NavigationApiError
from Navigation_Bot.gui.dialogs.login_dialog import LoginDialog
from Navigation_Bot.gui.main_window.navigation_gui import NavigationGUI
from Navigation_Bot.gui.widgets.startup_splash import StartupSplash


def configure_process_streams() -> None:
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")

    faulthandler.enable(all_threads=True)


def login_with_dialog(client: NavigationApiClient) -> str:
    while True:
        login_dialog = LoginDialog()
        if login_dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        try:
            login_response = client.login(login_dialog.username, login_dialog.password)
        except NavigationApiError as exc:
            QMessageBox.warning(None, "Вход", f"Не удалось войти:\n{exc}")
            continue

        api_key = str(login_response.get("api_key") or "")
        if api_key:
            return api_key

        QMessageBox.warning(None, "Вход", "API не вернул ключ сессии.")


def resolve_session_api_key(config: DatabaseConfig, client: NavigationApiClient, splash: StartupSplash) -> str:
    if os.getenv("NAV_GUI_SKIP_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}:
        splash.update("Вход пропущен...", "Используется ключ из конфигурации")
        return config.api_key

    splash.finish()
    return login_with_dialog(client)


def ensure_startup_splash(splash: StartupSplash) -> StartupSplash:
    if splash.splash is not None and splash.splash.isVisible():
        return splash

    splash = StartupSplash()
    splash.show("Вход выполнен...", "Загрузка главного окна")
    return splash


def main() -> int:
    configure_process_streams()

    app = QApplication(sys.argv)
    splash = StartupSplash()
    splash.show("Запуск приложения...", "Чтение конфигурации")

    splash.update("Загрузка конфигурации...", "Подготовка подключения к API")
    config = DatabaseConfig.from_env()
    client = NavigationApiClient(config.api_base_url)
    session_api_key = resolve_session_api_key(config, client, splash)
    splash = ensure_startup_splash(splash)

    splash.update("Создание главного окна...", "Загрузка компонентов интерфейса")
    window = NavigationGUI(api_key=session_api_key, startup_splash=splash)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
