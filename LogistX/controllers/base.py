# LogistX/controllers/onec/base.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

import pyautogui
import pydirectinput as pdi
import pyperclip
import pytesseract

from LogistX.controllers.visionLocator import VisionLocator

LogFunc = Callable[[str], Any]


@dataclass(frozen=True)
class OneCPaths:
    logistx_dir: Path
    ui_map_path: Path
    templates_dir: Path
    tmp_dir: Path


class OneCBase:
    def __init__(self, rdp_activator, log_func: LogFunc = print, ui_map_path=None):
        self.log: LogFunc = log_func
        self.rdp_activator = rdp_activator

        # tesseract (как у тебя в обоих файлах)
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        logistx_dir = Path(__file__).resolve().parents[2]  # .../LogistX
        if ui_map_path is None:
            ui_map_path = logistx_dir / "config" / "onec_ui_map.json"
        else:
            ui_map_path = Path(ui_map_path)
            if not ui_map_path.is_absolute():
                ui_map_path = logistx_dir / ui_map_path

        self.paths = OneCPaths(
            logistx_dir=logistx_dir,
            ui_map_path=ui_map_path,
            templates_dir=logistx_dir / "assets" / "onec_templates",
            tmp_dir=logistx_dir / "tmp"
        )
        self.paths.tmp_dir.mkdir(parents=True, exist_ok=True)

        self.ui = json.loads(self.paths.ui_map_path.read_text(encoding="utf-8"))
        vision_cfg = self.ui.get("vision", {})
        self.vision = VisionLocator(
            templates_dir=self.paths.templates_dir,
            threshold=float(vision_cfg.get("threshold", 0.82)),
            log_func=log_func,
        )

        pyautogui.FAILSAFE = True

    # ---------- infra helpers ----------
    def sleep(self, s: float = 0.2):
        time.sleep(s)

    def click_rect(self, rect):
        x1, y1, x2, y2 = rect
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        pyautogui.click(cx, cy)
        self.sleep(0.15)

    def fmt_dt(self, s: str) -> str:
        s = (s or "").strip()
        if not s:
            return s
        if len(s) >= 16 and s.count(":") >= 2:
            return s[:16]
        return s

    def click_button(self, btn_name: str) -> bool:
        rect = self.ui.get("buttons", {}).get(btn_name)
        if not rect:
            self.log(f"❌ Нет кнопки '{btn_name}' в ui_map")
            return False
        self.log(f"→ Кнопка: {btn_name}")
        self.click_rect(rect)
        self.sleep(0.4)
        return True

    def goto_race_params(self) -> bool:
        return self.click_button("race_params")

    def press_ok(self):
        self.log("→ Сохранение (Ctrl+Enter)")
        pyautogui.hotkey("ctrl", "enter")
        self._sleep(0.9)

    def cancel_and_close(self):
        self.log("↩️ Отмена/закрытие (Esc x2)")
        pyautogui.press("esc")
        self._sleep(0.2)
        # pyautogui.press("esc"); self._sleep(0.2)

    def paste_remote(self, text: str):
        pyperclip.copy(text)
        self._sleep(0.08)

        # 1) пытаемся вставить через pydirectinput (стабильнее в RDP)
        try:
            pdi.keyDown("ctrl")
            pdi.press("v")
            pdi.keyUp("ctrl")
            self._sleep(0.08)
            return
        except Exception:
            pass

        # 2) fallback на pyautogui ctrl+v
        try:
            pyautogui.keyDown("ctrl")
            pyautogui.press("v")
            pyautogui.keyUp("ctrl")
            self._sleep(0.08)
            return
        except Exception:
            pass

        # 3) ещё один fallback для RDP: Shift+Insert
        pyautogui.keyDown("shift")
        pyautogui.press("insert")
        pyautogui.keyUp("shift")
        self._sleep(0.08)

    def click_button(self, btn_name: str) -> bool:
        rect = self.ui["buttons"].get(btn_name)
        if not rect:
            return False
        self.log(f"→ Кнопка: {btn_name}")
        self._click_rect(rect)
        self._sleep(0.4)
        return True

    def click_menu_open(self) -> bool:
        # скрин маленькой области вокруг меню (примерно)
        region = (175, 270, 765, 800)  # подстроим потом
        left, top, w, h = region

        ts = int(time.time() * 1000)
        shot_path = (self.tmp_dir / f"menu_{ts}.png").resolve()
        self.vision.screenshot(shot_path, region=region)

        m = self.vision.find(shot_path, "menu_open.png", region_offset=(left, top))
        if not m:
            self.log("❌ Не нашёл пункт меню 'Открыть'")
            return False
        # try:
        #     shot_path.unlink()
        # except Exception:
        #     pass
        x, y = m.center
        pyautogui.click(x, y)
        self._sleep(1.2)
        return True

    def ctrl_f(self):
        # pydirectinput не имеет hotkey()
        try:
            pdi.keyDown("ctrl")
            pdi.press("f")
            pdi.keyUp("ctrl")
        except Exception:
            # fallback на pyautogui
            pyautogui.hotkey("ctrl", "f")
        self._sleep(0.2)

    def type_into_current_field(self, value: str):
        pyautogui.hotkey("ctrl", "a", interval=0.03)
        self._sleep(0.03)
        self._paste_remote(value)
        self._sleep(0.05)
        pyautogui.press("enter")
        self._sleep(0.10)

    def _close_error_dialog(self):
        # чаще всего ОК = Enter
        self._sleep(0.2)
        pdi.press("enter")
        self._sleep(0.2)
        print("Нажат Enter")
