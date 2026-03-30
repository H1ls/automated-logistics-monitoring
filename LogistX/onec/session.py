# LogistX/controllers/onec/session.py
from __future__ import annotations

import time
from pathlib import Path

import pyautogui
import pydirectinput as pdi
import pyperclip

from LogistX.controllers.visionLocator import VisionLocator
from .uimap import UiMap


class OneCSession:
    def __init__(self, rdp_activator, ui_map: UiMap,
                 templates_dir: str | Path, tmp_dir: str | Path,
                 log_func=print,
                 threshold: float = 0.82, ):

        self.rdp_activator = rdp_activator
        self.ui_map = ui_map
        self.log = log_func

        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        self.vision = VisionLocator(templates_dir=templates_dir, threshold=threshold, log_func=log_func, )
        self.ui_calibrated = False
        pyautogui.FAILSAFE = True

    # ------------------ base helpers ------------------

    def sleep(self, sec: float = 0.2):
        time.sleep(sec)

    def activate(self) -> bool:
        """
        Активируем RDP/1C окно.
        Ожидаем, что rdp_activator уже существует в проекте.
        """
        try:
            self.rdp_activator()
            self.sleep(0.8)
            return True
        except Exception as e:
            self.log(f"❌ Не удалось активировать RDP/1C: {e}")
            return False

    def press(self, key: str):
        try:
            pdi.press(key)
        except Exception:
            pyautogui.press(key)
        self.sleep(0.08)

    def hotkey(self, *keys: str, interval: float = 0.03):
        try:
            if len(keys) == 2:
                pdi.keyDown(keys[0])
                pdi.press(keys[1])
                pdi.keyUp(keys[0])
            else:
                pyautogui.hotkey(*keys, interval=interval)
        except Exception:
            pyautogui.hotkey(*keys, interval=interval)
        self.sleep(0.08)

    def copy_clipboard(self) -> str:
        try:
            return (pyperclip.paste() or "").strip()
        except Exception:
            return ""

    def clear_clipboard(self):
        try:
            pyperclip.copy("")
        except Exception:
            pass

    def paste_text(self, text: str):
        pyperclip.copy(text)
        self.sleep(0.08)

        try:
            pdi.keyDown("ctrl")
            pdi.press("v")
            pdi.keyUp("ctrl")
            self.sleep(0.08)
            return
        except Exception:
            pass

    def click(self, x: int, y: int):
        pyautogui.click(int(x), int(y))
        self.sleep(0.12)

    def double_click(self, x: int, y: int):
        pyautogui.doubleClick(int(x), int(y))
        self.sleep(0.20)

    def click_anchor(self, name: str):
        x, y = self.ui_map.get_anchor(name)
        # self.log(f"→ click anchor: {name} @ ({x}, {y})")
        self.click(x, y)

    def move_and_click_anchor(self, name: str):
        x, y = self.ui_map.get_anchor(name)
        pyautogui.moveTo(x, y, duration=0.05)
        self.click(x, y)

    def select_all(self):
        self.hotkey("ctrl", "a")

    def copy_current(self) -> str:
        self.clear_clipboard()
        self.hotkey("ctrl", "c")
        self.sleep(0.12)
        txt = self.copy_clipboard()
        if txt:
            return txt

        self.hotkey("ctrl", "insert")
        self.sleep(0.12)
        return self.copy_clipboard()

    def replace_current_field(self, value: str, submit: bool = False):
        self.select_all()
        self.sleep(0.03)
        self.paste_text(value)
        self.sleep(0.08)
        if submit:
            self.press("enter")

    # def replace_current_field(self, text: str, submit: bool = False):
    #     self.hotkey("ctrl", "a")
    #     self.sleep(0.05)
    #     self.press("backspace")
    #     self.sleep(0.05)
    #     self.paste_text(text)
    #     self.sleep(0.05)
    #     if submit:
    #         self.press("enter")
    def click_field_and_set_value(self, anchor_name: str, value: str, enter: bool = True):
        x, y = self.ui_map.get_anchor(anchor_name)
        self.click(x, y)
        self.sleep(0.08)
        self.press("f2")
        self.sleep(0.08)
        self.paste_text(value)
        self.sleep(0.05)
        if enter:
            self.press("enter")

    def screenshot_region(self, region_name: str, filename: str):
        region = self.ui_map.get_region(region_name)
        path = self.tmp_dir / filename
        return self.vision.screenshot(path, region=region)

    def find_template_global(self, template_name: str, region=None):
        if region is None:
            region = (0, 0, 1920, 1080)
        left, top, w, h = region
        path = self.tmp_dir / f"global_{template_name}.png"
        self.vision.screenshot(path, region=region)
        return self.vision.find(path, self.ui_map.get_template(template_name), region_offset=(left, top))

    def safe_close_card(self):
        self.log("↩️ Безопасное закрытие карточки/диалога")
        # self.press("esc")
        self.sleep(0.20)
        # self.press("esc")
        self.sleep(0.20)

    def submit_ctrl_enter(self):
        self.log("→ Ctrl+Enter")
        self.hotkey("ctrl", "enter")
        self.sleep(0.7)

    def capture_current_race_form(self, filename: str = "race_form.png"):
        return self.vision.screenshot(self.tmp_dir / filename)

    def find_template_on_shot(self, shot_path, template_name: str):
        template_file = self.ui_map.get_template(template_name)
        return self.vision.find(shot_path, template_file)

    def find_template_in_region(self, template_name: str, region_name: str):
        region = self.ui_map.get_region(region_name)
        left, top, w, h = region
        path = self.screenshot_region(region_name, f"{region_name}_{template_name}.png")
        return self.vision.find(path, self.ui_map.get_template(template_name), region_offset=(left, top))

    def capture_full(self, filename: str = "race_form.png"):
        path = self.tmp_dir / filename
        shot = pyautogui.screenshot()
        shot.save(path)
        return path

    def capture_region(self, region_name: str, filename: str):
        region = self.ui_map.get_region(region_name)
        x, y, w, h = region
        path = self.tmp_dir / filename
        shot = pyautogui.screenshot(region=(x, y, w, h))
        shot.save(path)
        return path

    def capture_current_race_form(self, filename: str = "race_form.png"):
        # Пока берём полный экран, можно заменить на region "race_form_region", если добавишь его в json.
        return self.capture_full(filename)

    def find_template_on_shot(self, shot_path, template_name: str):
        template_file = self.ui_map.get_template(template_name)
        return self.vision.find(shot_path, template_file)

    def find_template_in_region(self, template_name: str, region_name: str, filename: str | None = None):
        filename = filename or f"{template_name}__{region_name}.png"
        shot_path = self.capture_region(region_name, filename)
        return self.find_template_on_shot(shot_path, template_name)

    def copy_cell_text(self, x: int, y: int) -> str:
        self.click(x, y)
        self.sleep(0.08)
        self.press("f2")
        self.sleep(0.08)
        text = self.copy_current()
        # self.press("esc")
        self.sleep(0.05)
        return (text or "").strip()

    def replace_cell(self, x: int, y: int, value: str, submit: bool = True):
        self.click(x, y)
        self.sleep(0.08)
        self.press("f2")
        self.sleep(0.08)
        self.replace_current_field(value, submit=submit)

    def screenshot_full(self, name: str):
        path = self.tmp_dir / name
        img = pyautogui.screenshot()
        img.save(path)
        return str(path)