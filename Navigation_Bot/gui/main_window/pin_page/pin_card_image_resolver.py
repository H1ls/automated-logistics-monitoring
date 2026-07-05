from __future__ import annotations

from pathlib import Path

from Navigation_Bot.core.domain.entities.pin_code import normalize_pin_text


class PinCardImageResolver:
    SUPPLIER_IMAGE_CODES = {
        "ППР": "ppr",
        "РНКАРТ": "RN",
        "РНКАРТА": "RN",
        "ТРАНСНЕФТЬПРОДУКТ": "TNP",
        "ТРАНСНЕФТЕПРОДУКТ": "TNP",
        "ЦЕНТРОТЕХАЗСОПТ": "OPTI",
    }

    def __init__(self, images_dir: str | Path):
        self.images_dir = Path(images_dir)

    @staticmethod
    def supplier_key(value: str) -> str:
        key = normalize_pin_text(value)
        for ch in ("-", "‑", "–", "—", "_", ".", ",", "(", ")", "/", "\\"):
            key = key.replace(ch, "")
        return key

    def image_path_for(self, supplier: str) -> Path | None:
        supplier_key = self.supplier_key(supplier)
        code = self.SUPPLIER_IMAGE_CODES.get(supplier_key)
        if not code:
            for key, value in self.SUPPLIER_IMAGE_CODES.items():
                if supplier_key.startswith(key) or key in supplier_key:
                    code = value
                    break
        if not code:
            return None

        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = self.images_dir / f"{code}{ext}"
            if path.exists():
                return path
        return None
