from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import pyautogui


@dataclass
class Match:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


class VisionLocator:
    def __init__(self, templates_dir: str | Path, threshold: float = 0.82, log_func=print):
        self.templates_dir = Path(templates_dir)
        self.threshold = float(threshold)
        self.log = log_func

    def screenshot(self, path: str | Path, region: Optional[tuple[int, int, int, int]] = None) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        img = pyautogui.screenshot(region=region)
        img.save(path)
        return path

    def find(self, screenshot_path: str | Path, template_name: str, region_offset=(0, 0)) -> Optional[Match]:
        """
        region_offset: (left, top) если скрин сделан из region (чтобы вернуть координаты экрана)
        """
        screenshot_path = str(screenshot_path)
        template_path = self.templates_dir / template_name
        if not template_path.exists():
            self.log(f"❌ template not found: {template_path}")
            return None

        img = cv2.imread(screenshot_path, cv2.IMREAD_COLOR)
        tmpl = cv2.imread(str(template_path), cv2.IMREAD_COLOR)

        if img is None or tmpl is None:
            self.log("❌ cv2 failed to read images")
            return None

        res = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val < self.threshold:
            # self.log(f"⚠️ template '{template_name}' not found. score={max_val:.3f}")
            return None

        h, w = tmpl.shape[:2]
        ox, oy = region_offset
        x = int(max_loc[0] + ox)
        y = int(max_loc[1] + oy)
        return Match(x=x, y=y, w=w, h=h, score=float(max_val))