from __future__ import annotations

from PIL import Image, ImageOps

from LogistX.onec.artifacts import OneCArtifacts


class CheckboxController:
    """Считывает и идемпотентно устанавливает классические чекбоксы 1C по центру их квадратной области."""

    def __init__(self, session, artifacts=None, log_func=print, dark_pixel_threshold: int = 3):
        self.session = session
        self.artifacts = artifacts or getattr(session, "artifacts", None) or OneCArtifacts(session, log_func=log_func)
        self.log = log_func
        self.dark_pixel_threshold = int(dark_pixel_threshold)

    def is_checked(self, center: tuple[int, int], stage: str, name: str) -> bool:
        x, y = map(int, center)
        radius_x, radius_y = self.session.ui_map.scale_point(4, 4)
        radius_x, radius_y = max(3, radius_x), max(3, radius_y)
        width, height = radius_x * 2 + 1, radius_y * 2 + 1
        path = self.artifacts.capture_rect(
            stage, f"checkbox_{name}", (x - radius_x, y - radius_y, width, height)
        )
        with Image.open(path) as source:
            pixels = list(ImageOps.grayscale(source).getdata())
        threshold = max(self.dark_pixel_threshold, round(len(pixels) * 0.04))
        return sum(1 for value in pixels if value < 128) >= threshold

    def ensure_checked(self, center: tuple[int, int], stage: str, name: str) -> bool:
        if self.is_checked(center, stage, name):
            self.log(f"☑️ Checkbox '{name}' уже установлен")
            return False

        self.session.click(*center)
        self.session.sleep(0.2)
        if not self.is_checked(center, stage, name):
            raise RuntimeError(f"Не удалось установить checkbox '{name}'")
        self.log(f"☑️ Checkbox '{name}' установлен")
        return True
