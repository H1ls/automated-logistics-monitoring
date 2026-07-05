import sys, faulthandler
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QSplashScreen
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


class StartupSplash:
    def __init__(self):
        pixmap = QPixmap(520, 260)
        pixmap.fill(QColor("#20232a"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        title_font = QFont()
        title_font.setPointSize(22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(34, 58, "Navigation Manager")

        subtitle_font = QFont()
        subtitle_font.setPointSize(10)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#b8c0cc"))
        painter.drawText(36, 88, "Подготовка приложения")

        painter.setPen(QColor("#4caf50"))
        painter.setBrush(QColor("#4caf50"))
        painter.drawRoundedRect(36, 198, 448, 6, 3, 3)
        painter.end()

        self.splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        self.splash.setWindowFlag(Qt.WindowType.FramelessWindowHint)

    def show(self, text: str, detail: str = "") -> None:
        if self.splash is None:
            return
        self.splash.show()
        self.update(text, detail)

    def update(self, text: str, detail: str = "") -> None:
        if self.splash is None:
            return
        message = text if not detail else f"{text}\n{detail}"
        self.splash.showMessage(message,
                                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                                QColor("#ffffff")
                                )
        QApplication.processEvents()

    def finish(self, widget=None) -> None:
        if self.splash is None:
            return
        if widget is not None:
            self.splash.finish(widget)
        else:
            self.splash.close()
        self.splash.hide()
        self.splash.deleteLater()
        self.splash = None
        QApplication.processEvents()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash = StartupSplash()
    splash.show("Запуск приложения...", "Чтение конфигурации")

    splash.update("Загрузка конфигурации...", "Подготовка подключения к API")
    config = DatabaseConfig.from_env()
    client = NavigationApiClient(config.api_base_url)
    session_api_key = ""

    if os.getenv("NAV_GUI_SKIP_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}:
        splash.update("Вход пропущен...", "Используется ключ из конфигурации")
        session_api_key = config.api_key

    if not session_api_key:
        splash.finish()
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

    if splash.splash is None or not splash.splash.isVisible():
        splash = StartupSplash()
        splash.show("Вход выполнен...", "Загрузка главного окна")

    splash.update("Создание главного окна...", "Загрузка компонентов интерфейса")
    window = NavigationGUI(api_key=session_api_key, startup_splash=splash)

    sys.exit(app.exec())
