from PyQt6.QtCore import QTimer


class DialogRequestController:
    def __init__(self, gui, interval_ms: int = 50):
        self.gui = gui
        self.interval_ms = interval_ms
        self.timer = QTimer(gui)
        self.timer.timeout.connect(self.process_pending)

    def start(self) -> None:
        if self.timer.isActive():
            self.gui.log("⚠️ Таймер диалогов уже активен, пропускаем запуск")
            return
        self.timer.start(self.interval_ms)

    def stop(self) -> None:
        if self.timer.isActive():
            self.timer.stop()

    def process_pending(self) -> None:
        try:
            processor = getattr(self.gui, "processor", None)
            if processor:
                processor.process_pending_dialog_requests()
        except Exception as e:
            self.gui.log(f"⚠️ Ошибка обработки запросов диалогов: {e}")
