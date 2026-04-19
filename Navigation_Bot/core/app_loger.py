class AppLogger:
    def __init__(self, log_func=None, prefix=""):
        self.log_func = log_func
        self.prefix = prefix

    def info(self, msg):
        self._log("INFO", msg)

    def error(self, msg):
        self._log("ERROR", msg)

    def _log(self, level, msg):
        text = f"[{level}] [{self.prefix}] {msg}"
        if self.log_func:
            self.log_func(text)