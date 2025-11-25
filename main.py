import sys
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

if __name__ == "__main__":
    app = QApplication(sys.argv)

    from Navigation_Bot.gui.dialogs.loginDialog import LoginDialog
    from Navigation_Bot.gui.main_window.Gui import NavigationGUI
    from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager

    gsheet = GoogleSheetsManager(log_func=print)

    while True:
        login_dialog = LoginDialog()
        result = login_dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            sys.exit(0)

        login = login_dialog.login
        password = login_dialog.password

        ok, msg = gsheet.check_user_credentials(login, password)

        if ok:
            break
        else:
            QMessageBox.warning(None, "Вход", msg)

    window = NavigationGUI()
    window.show()

    sys.exit(app.exec())
