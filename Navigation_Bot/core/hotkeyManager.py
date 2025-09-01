import time
import pyclip
import keyboard
from datetime import datetime
from threading import Thread, Event
from global_hotkeys import register_hotkeys, start_checking_hotkeys, stop_checking_hotkeys


class HotkeyManager:
    def __init__(self, log_func=print):
        self.log = log_func
        self.clipboard_history = []
        self.use_dual_clipboard = False
        self._running = Event()
        self._thread = None

    def _get_time(self):
        return datetime.now().strftime("%d.%m %H:%M")

    def _update_clipboard_history(self):
        try:
            current_raw = pyclip.paste()
            current = current_raw.decode("utf-8") if isinstance(current_raw, bytes) else current_raw
            current = current.strip()
            if self.clipboard_history and self.clipboard_history[-1] == current:
                return
            if current:
                self.clipboard_history.append(current)
                if len(self.clipboard_history) > 10:
                    self.clipboard_history.pop(0)
        except Exception:
            pass

    def _get_last_two_parts(self):
        self._update_clipboard_history()

        if not self.clipboard_history:
            return "(нет данных)", ""

        if not self.use_dual_clipboard:
            part = self.clipboard_history[-1].splitlines()[0].strip()
            return self.clipboard_history[-1], part

        if len(self.clipboard_history) >= 2:
            buf1 = self.clipboard_history[-2].splitlines()[0].strip()
            buf2 = self.clipboard_history[-1].splitlines()[0].strip()
            if buf1 != buf2:
                return self.clipboard_history[-2] + "\n---\n" + self.clipboard_history[-1], f"{buf1} {buf2}"
            else:
                return self.clipboard_history[-1], buf1
        else:
            part = self.clipboard_history[-1].splitlines()[0].strip()
            return self.clipboard_history[-1], part

    def _write_status(self, status: str):
        source, parts = self._get_last_two_parts()
        if parts:
            result = f"{self._get_time()} {status} {parts}"
            keyboard.write(result)

    def _write_there(self):
        keyboard.write(f"{self._get_time()} там же ")

    def _write_time(self):
        keyboard.write(self._get_time() + " ")

    def _toggle_mode(self):
        self.use_dual_clipboard = not self.use_dual_clipboard
        mode_text = "РЕЖИМ: два буфера" if self.use_dual_clipboard else "РЕЖИМ: один буфер"
        self.log(f"[{self._get_time()}] {mode_text}")

    def _loop(self):
        bindings = [
            ["control + alt", None, self._write_time, False],
            ["alt + 1", None, lambda: self._write_status("едет"), False],
            ["alt + 2", None, lambda: self._write_status("стоит"), False],
            ["alt + 3", None, self._write_there, False],
            ["F1", None, self._toggle_mode, False],
        ]
        register_hotkeys(bindings)
        start_checking_hotkeys()

        while self._running.is_set():
            self._update_clipboard_history()
            time.sleep(0.1)

        stop_checking_hotkeys()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log("▶ HotkeyManager запущен")

    def stop(self):
        if self._running.is_set():
            self._running.clear()
            self.log("⏹ HotkeyManager остановлен")
