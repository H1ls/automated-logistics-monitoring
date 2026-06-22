import sys, faulthandler
import os
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from Navigation_Bot.core.database_config import DatabaseConfig
from Navigation_Bot.core.infrastructure.api.api_client import NavigationApiClient, NavigationApiError
from Navigation_Bot.gui.dialogs.login_dialog import LoginDialog
from Navigation_Bot.gui.main_window.navigation_gui import NavigationGUI

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
faulthandler.enable(all_threads=True)

from pathlib import Path
import sys

base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

if __name__ == "__main__":
    app = QApplication(sys.argv)

    config = DatabaseConfig.from_env()
    client = NavigationApiClient(config.api_base_url)
    session_api_key = ""

    if os.getenv("NAV_GUI_SKIP_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}:
        session_api_key = config.api_key

    if not session_api_key:
        while True:
            login_dialog = LoginDialog()
            if login_dialog.exec() != QDialog.DialogCode.Accepted:
                sys.exit(0)
            try:
                login_response = client.login(login_dialog.username, login_dialog.password)
            except NavigationApiError as exc:
                QMessageBox.warning(None, "Вход", f"Не удалось войти:\n{exc}")
                continue
            session_api_key = str(login_response.get("api_key") or "")
            if session_api_key:
                break
            QMessageBox.warning(None, "Вход", "API не вернул ключ сессии.")

    window = NavigationGUI(api_key=session_api_key)
    window.show()

    sys.exit(app.exec())
