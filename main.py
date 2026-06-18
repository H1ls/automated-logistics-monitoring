import sys, faulthandler
import os
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
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

    # gsheet = GoogleSheetsManager(log_func=print)

    # while True:
    #     login_dialog = LoginDialog()
    #     result = login_dialog.exec()
    #
    #     if result != QDialog.DialogCode.Accepted:
    #         sys.exit(0)
    #
    #     login = login_dialog.login
    #     password = login_dialog.password
    #
    #     ok, msg = gsheet.check_user_credentials(login, password)
    #
    #     if ok:
    #         break
    #     else:
    #         QMessageBox.warning(None, "Вход", msg)

    window = NavigationGUI()
    window.show()

    sys.exit(app.exec())
