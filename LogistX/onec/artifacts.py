from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw


class OneCArtifacts:
    """Создавай и называй скриншоты 1С по шаблону"""

    def __init__(self, session, enabled: bool = False, log_func=print):
        self.session = session
        self.enabled = bool(enabled)
        self.log = log_func

    @staticmethod
    def _slug(value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip())
        return value.strip("_") or "artifact"

    def filename(self, stage: str, name: str) -> str:
        return f"{self._slug(stage)}__{self._slug(name)}.png"

    def capture_full(self, stage: str, name: str, *, debug_only: bool = False) -> Path | None:
        if debug_only and not self.enabled:
            return None
        return Path(self.session.capture_full(self.filename(stage, name)))

    def capture_region(self, stage: str, name: str, region_name: str) -> Path:
        return Path(self.session.capture_region(region_name, self.filename(stage, name)))

    def capture_rect(self, stage: str, name: str, rect: tuple[int, int, int, int]) -> Path:
        path = Path(self.session.tmp_dir) / self.filename(stage, name)
        return Path(self.session.vision.screenshot(path, region=rect))

    def annotate_points(self, source_path: str | Path, stage: str, name: str,
                        points: list[tuple[str, int, int]], *, origin=(0, 0)) -> Path | None:
        if not self.enabled:
            return None

        output = Path(self.session.tmp_dir) / self.filename(stage, name)
        origin_x, origin_y = origin
        with Image.open(source_path).convert("RGB") as image:
            draw = ImageDraw.Draw(image)
            for label, x_abs, y_abs in points:
                x = int(x_abs) - int(origin_x)
                y = int(y_abs) - int(origin_y)
                radius = 8
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="red", width=3)
                draw.text((x + 10, y - 10), str(label), fill="red")
            image.save(output)

        self.log(f"🧪 debug points: {output}")
        return output

    def annotate_regions(self, source_path: str | Path, stage: str, name: str,
                         region_names: list[str]) -> Path | None:
        if not self.enabled:
            return None

        output = Path(self.session.tmp_dir) / self.filename(stage, name)
        with Image.open(source_path).convert("RGB") as image:
            draw = ImageDraw.Draw(image)
            for region_name in region_names:
                left, top, width, height = self.session.ui_map.get_region(region_name)
                draw.rectangle((left, top, left + width, top + height), outline="yellow", width=3)
                draw.text((left + 5, top + 5), region_name, fill="yellow")
            image.save(output)

        self.log(f"🧭 debug regions: {output}")
        return output
