# LogistX/onec/uimap.py
from __future__ import annotations

import json
from pathlib import Path

from Navigation_Bot.core.json_store import JsonStore


class UiMap:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        reference = self.data.get("reference_screen") or [1920, 1080]
        self.reference_screen = int(reference[0]), int(reference[1])
        self.viewport = self.reference_screen

    def set_viewport(self, width: int, height: int) -> None:
        self.viewport = max(1, int(width)), max(1, int(height))

    @property
    def scale(self) -> tuple[float, float]:
        ref_w, ref_h = self.reference_screen
        width, height = self.viewport
        return width / ref_w, height / ref_h

    def scale_point(self, x: int | float, y: int | float) -> tuple[int, int]:
        sx, sy = self.scale
        return round(float(x) * sx), round(float(y) * sy)

    def unscale_point(self, x: int | float, y: int | float) -> tuple[int, int]:
        sx, sy = self.scale
        return round(float(x) / sx), round(float(y) / sy)

    def save(self):
        JsonStore(log_func=lambda *_: None).save_in_json(self.data, self.path)

    def get_anchor(self, name: str) -> tuple[int, int]:
        anchors = self.data.get("anchors", {})
        point = anchors.get(name)
        if not point:
            raise KeyError(f"Anchor '{name}' not found in {self.path}")
        return self.scale_point(point[0], point[1])

    def set_anchor(self, name: str, x: int, y: int):
        self.data.setdefault("anchors", {})
        ref_x, ref_y = self.unscale_point(x, y)
        self.data["anchors"][name] = [ref_x, ref_y]

    def clear_anchors(self, names: tuple[str, ...] | list[str]) -> int:
        """Удаляет якоря калибровки по имени. Возвращает число удалённых."""
        anchors = self.data.setdefault("anchors", {})
        removed = 0
        for name in names:
            if name in anchors:
                del anchors[name]
                removed += 1
        if removed:
            self.save()
        return removed

    def get_region(self, name: str) -> tuple[int, int, int, int]:
        regions = self.data.get("regions", {})
        region = regions.get(name)
        if not region:
            raise KeyError(f"Region '{name}' not found in {self.path}")
        x, y = self.scale_point(region[0], region[1])
        width, height = self.scale_point(region[2], region[3])
        return x, y, width, height

    def get_template(self, name: str) -> str:
        templates = self.data.get("templates", {})
        value = templates.get(name)
        if not value:
            raise KeyError(f"Template '{name}' not found in {self.path}")
        return value

    def get_optional_anchor(self, name: str):
        anchors = self.data.get("anchors", {})
        point = anchors.get(name)
        if not point:
            return None
        return self.scale_point(point[0], point[1])

    def get_optional_region(self, name: str):
        regions = self.data.get("regions", {})
        region = regions.get(name)
        if not region:
            return None
        x, y = self.scale_point(region[0], region[1])
        width, height = self.scale_point(region[2], region[3])
        return x, y, width, height

    def get_optional_template(self, name: str):
        return self.data.get("templates", {}).get(name)

    def get_offset(self, name: str) -> tuple[int, int]:
        offsets = self.data.get("offsets", {})
        value = offsets.get(name)
        if not value:
            raise KeyError(f"Offset '{name}' not found in {self.path}")
        return self.scale_point(value[0], value[1])

    def get_optional_offset(self, name: str):
        offsets = self.data.get("offsets", {})
        value = offsets.get(name)
        if not value:
            return None
        return self.scale_point(value[0], value[1])

    # def get_window_title_hint(self) -> str:
    #     return self.data.get("window", {}).get("title_hint", "")
