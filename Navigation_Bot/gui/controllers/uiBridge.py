from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

class UiBridge(QObject):
    set_busy = pyqtSignal(int, bool)   # index_key, busy
    refresh = pyqtSignal()
    log = pyqtSignal(str)

    def __init__(self, gui):
        super().__init__(gui)  # важно: родитель = GUI (живёт в GUI-потоке)
        self.gui = gui

        self.set_busy.connect(self._on_set_busy)
        self.refresh.connect(self._on_refresh)
        self.log.connect(self._on_log)

    @pyqtSlot(int, bool)
    def _on_set_busy(self, index_key: int, busy: bool):
        self.gui.table_manager.set_row_busy(index_key, busy)

    @pyqtSlot()
    def _on_refresh(self):
        self.gui.reload_and_show()

    @pyqtSlot(str)
    def _on_log(self, msg: str):
        self.gui.log(msg)
