# LogistX/onec/uimap.py
from __future__ import annotations

import json
from pathlib import Path


class UiMap:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    """
    left, top, width, height
    width  = x2 - x1
    height = y2 - y1    
    [x1, y1, x2, y2]  ->  [x1, y1, x2-x1, y2-y1]
    """

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),encoding="utf-8",)

    def get_anchor(self, name: str) -> tuple[int, int]:
        anchors = self.data.get("anchors", {})
        point = anchors.get(name)
        if not point:
            raise KeyError(f"Anchor '{name}' not found in {self.path}")
        return int(point[0]), int(point[1])

    def set_anchor(self, name: str, x: int, y: int):
        self.data.setdefault("anchors", {})
        self.data["anchors"][name] = [int(x), int(y)]

    def get_region(self, name: str) -> tuple[int, int, int, int]:
        regions = self.data.get("regions", {})
        region = regions.get(name)
        if not region:
            raise KeyError(f"Region '{name}' not found in {self.path}")
        return tuple(map(int, region))

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
        return int(point[0]), int(point[1])

    def get_optional_region(self, name: str):
        regions = self.data.get("regions", {})
        region = regions.get(name)
        if not region:
            return None
        return tuple(map(int, region))

    def get_optional_template(self, name: str):
        return self.data.get("templates", {}).get(name)

    def get_offset(self, name: str) -> tuple[int, int]:
        offsets = self.data.get("offsets", {})
        value = offsets.get(name)
        if not value:
            raise KeyError(f"Offset '{name}' not found in {self.path}")
        return int(value[0]), int(value[1])

    def get_optional_offset(self, name: str):
        offsets = self.data.get("offsets", {})
        value = offsets.get(name)
        if not value:
            return None
        return int(value[0]), int(value[1])

    def get_window_title_hint(self) -> str:
        return self.data.get("window", {}).get("title_hint", "")
