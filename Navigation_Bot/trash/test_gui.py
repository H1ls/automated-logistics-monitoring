from PyQt6.QtWidgets import QApplication, QLabel, QWidget
import sys

app = QApplication(sys.argv)
window = QWidget()
window.setWindowTitle('Тестовое окно')
window.setGeometry(100, 100, 400, 300)
window.show()
sys.exit(app.exec())
