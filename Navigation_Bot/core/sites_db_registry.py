from __future__ import annotations

import json
import re

from LogistX.config.paths import SITES_DB_FILE

SITES_DB_PATH = SITES_DB_FILE


class SitesDbRegistry:
    """Читает sites_db.json и сопоставляет адреса с aliases/geofence."""

    def __init__(self, log_func=None):
        self.log = log_func or print
        self._data: list[dict] = []
        self.reload()

    def reload(self) -> None:
        try:
            if not SITES_DB_PATH.exists():
                self._data = []
                return
            raw = json.loads(SITES_DB_PATH.read_text(encoding="utf-8") or "[]")
            self._data = raw if isinstance(raw, list) else []
        except Exception as e:
            self.log(f"Ошибка чтения sites_db.json: {e}")
            self._data = []

    @staticmethod
    def _norm(value: str) -> str:
        s = (value or "").lower().replace("ё", "е")
        s = re.sub(r"[^\w\s]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def resolve_geofence(self, address: str) -> str:
        addr_n = self._norm(address)
        if not addr_n or not self._data:
            return ""

        best = ""
        best_score = 0
        for obj in self._data:
            aliases = obj.get("aliases") or []
            if not isinstance(aliases, list):
                continue

            score = 0
            for alias in aliases:
                alias_n = self._norm(str(alias))
                if alias_n and alias_n in addr_n:
                    score += 1

            if score > best_score:
                best_score = score
                best = str(obj.get("geofence", "") or "")

        return best if best_score > 0 else ""

    def is_address_known(self, address: str) -> bool:
        return bool(self.resolve_geofence(address))

    @staticmethod
    def collect_point_addresses(blocks: list, prefix: str) -> list[str]:
        points = []
        for d in blocks or []:
            if not isinstance(d, dict):
                continue
            if "Комментарий" in d or f"{prefix} другое" in d:
                continue
            if any(k.startswith(f"{prefix} ") for k in d.keys()):
                points.append(d)

        addresses = []
        for i, block in enumerate(points, 1):
            addr = str(block.get(f"{prefix} {i}", "") or "").strip()
            if addr:
                addresses.append(addr)
        return addresses

    def match_geo_zona_to_zone_label(self, geo_zona: str, item: dict) -> str | None:
        zone_norm = self._norm(geo_zona)
        if not zone_norm:
            return None

        for addr in self.collect_point_addresses(item.get("Погрузка", []), "Погрузка"):
            load_fence = self._norm(self.resolve_geofence(addr))
            if load_fence and load_fence == zone_norm:
                return "Погрузка"

        for addr in self.collect_point_addresses(item.get("Выгрузка", []), "Выгрузка"):
            unload_fence = self._norm(self.resolve_geofence(addr))
            if unload_fence and unload_fence == zone_norm:
                return "Выгрузка"

        return None
