from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from LogistX.config.paths import SITES_DB_FILE
from Navigation_Bot.core.logging import normalize_log_func

SITES_DB_PATH = SITES_DB_FILE


@dataclass(frozen=True, slots=True)
class SiteMatch:
    site_id: str
    geofence: str
    score: int


class SitesDbRegistry:
    """Читает sites_db.json и сопоставляет адреса с aliases/geofence."""

    def __init__(self, log_func=None, path: Path | None = None):
        self.log = normalize_log_func(log_func)
        self.path = path or SITES_DB_PATH
        self._data: list[dict] = []
        self.reload()

    @property
    def items(self) -> list[dict]:
        return self._data

    @items.setter
    def items(self, value: list[dict]) -> None:
        self._data = value if isinstance(value, list) else []

    def reload(self) -> None:
        try:
            if not self.path.exists():
                self._data = []
                return
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
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
        match = self.match(address)
        return match.geofence if match else ""

    def match(self, address: str) -> SiteMatch | None:
        addr_n = self._norm(address)
        if not addr_n or not self._data:
            return None

        best = None
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
                best = obj

        if best is None:
            return None
        return SiteMatch(site_id=str(best.get("site_id") or ""),
                         geofence=str(best.get("geofence") or ""),
                         score=best_score)

    def is_address_known(self, address: str) -> bool:
        return bool(self.resolve_geofence(address))

    @staticmethod
    def collect_point_addresses(blocks: list, prefix: str) -> list[str]:
        pattern = re.compile(rf"^{re.escape(prefix)}\s+(\d+)$")
        points: list[tuple[int, str]] = []
        for d in blocks or []:
            if not isinstance(d, dict):
                continue
            for key, value in d.items():
                match = pattern.match(str(key).strip())
                if not match:
                    continue
                address = str(value or "").strip()
                if address:
                    points.append((int(match.group(1)), address))
                break

        points.sort(key=lambda item: item[0])
        return [address for _, address in points]

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
