from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

RACE_CODE_RE = re.compile(r"\b[А-ЯA-Z]{2}\d{9}\b", re.IGNORECASE)
PLATE_RE = re.compile(r"[А-ЯA-Z]\s*\d{3}\s*[А-ЯA-Z]{2}\s*\d{2,3}", re.IGNORECASE)

_VISUAL_LATIN = str.maketrans({"А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
                               "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",})


@dataclass(frozen=True)
class RaceCardVerification:
    ok: bool
    race_ok: bool
    unit_ok: bool
    expected_race: str
    expected_plate: str
    recognized_text: str

    @property
    def failed_fields(self) -> list[str]:
        failed = []
        if not self.race_ok:
            failed.append("номер рейса")
        if not self.unit_ok:
            failed.append("номер машины")
        return failed


class RaceCardVerifier:
    REFERENCE_SIZE = (600, 560)
    FIELD_RECTS = {
        "race": (112, 148, 202, 176),
        "plate": (112, 319, 260, 348),
    }

    def __init__(self, ocr_func=None):
        self.ocr_func = ocr_func or self._read_image

    @staticmethod
    def _read_image(path: str | Path) -> str:
        with Image.open(path) as source:
            recognized = []
            for field, rect in RaceCardVerifier.FIELD_RECTS.items():
                ref_width, ref_height = RaceCardVerifier.REFERENCE_SIZE
                sx, sy = source.width / ref_width, source.height / ref_height
                scaled_rect = (
                    round(rect[0] * sx), round(rect[1] * sy),
                    round(rect[2] * sx), round(rect[3] * sy),
                )
                image = source.crop(scaled_rect)
                image = ImageOps.autocontrast(ImageOps.grayscale(image))
                image = image.resize((image.width * 4, image.height * 4))
                text = pytesseract.image_to_string(image,lang="rus+eng",config="--oem 3 --psm 7",).strip()
                recognized.append(f"{field}: {text}")
            return "\n".join(recognized)

    @staticmethod
    def _compact_identifier(value: str) -> str:
        value = str(value or "").upper().translate(_VISUAL_LATIN)
        return re.sub(r"[^A-Z0-9]", "", value).replace("O", "0")

    @staticmethod
    def _expected_race(ctx) -> str:
        match = RACE_CODE_RE.search(str(getattr(ctx, "race_name", "") or ""))
        return match.group(0) if match else ""

    @staticmethod
    def _expected_plate(ctx) -> str:
        meta = getattr(ctx, "meta", {}) or {}
        unit = str(meta.get("unit") or meta.get("ТС") or "")
        match = PLATE_RE.search(unit)
        return match.group(0) if match else ""

    def verify(self, ctx, image_path: str | Path) -> RaceCardVerification:
        recognized = str(self.ocr_func(image_path) or "")
        expected_race = self._expected_race(ctx)
        expected_plate = self._expected_plate(ctx)
        recognized_identifier = self._compact_identifier(recognized)

        race_ok = bool(expected_race) and self._compact_identifier(expected_race) in recognized_identifier
        unit_ok = bool(expected_plate) and self._compact_identifier(expected_plate) in recognized_identifier

        return RaceCardVerification(
            ok=race_ok and unit_ok,
            race_ok=race_ok,
            unit_ok=unit_ok,
            expected_race=expected_race,
            expected_plate=expected_plate,
            recognized_text=recognized,
        )
