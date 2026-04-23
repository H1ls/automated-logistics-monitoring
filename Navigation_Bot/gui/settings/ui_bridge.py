# Navigation_Bot\gui\controllers
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class UiBridge(QObject):
    set_busy = pyqtSignal(int, bool)  # index_key, busy
    refresh = pyqtSignal()
    log = pyqtSignal(str)
    call = pyqtSignal(object)
    fact_ready = pyqtSignal(int, str, object, dict)  # row, race_no, fd(datetime), payload(dict)

    def __init__(self, gui):
        super().__init__(gui)  # важно: родитель = GUI (живёт в GUI-потоке)
        self.gui = gui

        self.set_busy.connect(self._on_set_busy)
        self.refresh.connect(self._on_refresh)
        self.log.connect(self._on_log)
        self.call.connect(self._on_call)

    @pyqtSlot(int, str, object, dict)
    def _on_fact_ready(self, row, race_no, fd, payload):
        self.gui.processor._apply_fact_result(self.gui.page_logistx, row, race_no, fd, payload)

    @pyqtSlot(object)
    def _on_call(self, fn):
        fn()

    @pyqtSlot(int, bool)
    def _on_set_busy(self, index_key: int, busy: bool):
        self.gui.table_manager.set_row_busy(index_key, busy)

    @pyqtSlot()
    def _on_refresh(self):
        self.gui.reload_and_show()

    @pyqtSlot(str)
    def _on_log(self, msg: str):
        self.gui.log(msg)
