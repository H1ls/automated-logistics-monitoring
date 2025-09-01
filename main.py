# main.py
import sys
from PyQt6.QtWidgets import QApplication
from Navigation_Bot.gui.Gui import NavigationGUI

def main():
    app = QApplication(sys.argv)
    gui = NavigationGUI()
    gui.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
