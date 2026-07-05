from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

KNOWN_RATING_KINDS = ("Без отклонений",
                      "Опоздание на погрузку",
                      "Опоздание на разгрузку",
                      "Простой на погрузке",
                      "Простой на разгрузке")


@dataclass(frozen=True)
class RatingRow:
    kind: str
    hours: int
    y: int
    text: str

    @property
    def key(self) -> tuple[str, int]:
        return self.kind, self.hours


@dataclass(frozen=True)
class RatingTableSnapshot:
    rows: tuple[RatingRow, ...]
    recognized_text: str


class DriverRatingTableReader:
    def __init__(self, line_reader=None):
        self.line_reader = line_reader or self._read_lines

    @staticmethod
    def _normalize(value: str) -> str:
        value = str(value or "").casefold().replace("ё", "е")
        return " ".join(re.findall(r"[а-яa-z0-9]+", value, flags=re.IGNORECASE))

    @classmethod
    def _kind_score(cls, kind: str, line: str) -> float:
        kind_norm = cls._normalize(kind)
        line_norm = cls._normalize(line)
        if kind_norm in line_norm:
            return 1.0

        expected = kind_norm.split()
        actual = line_norm.split()
        scores = []
        for size in range(max(1, len(expected) - 1), len(expected) + 2):
            for index in range(0, len(actual) - size + 1):
                candidate = " ".join(actual[index:index + size])
                scores.append(SequenceMatcher(None, kind_norm, candidate).ratio())
        return max(scores, default=0.0)

    @staticmethod
    def _read_lines(path: str | Path) -> list[tuple[int, str]]:
        with Image.open(path) as source:
            image = ImageOps.autocontrast(ImageOps.grayscale(source))
            scale = 2
            image = image.resize((image.width * scale, image.height * scale))
            data = pytesseract.image_to_data(image, lang="rus+eng", config="--oem 3 --psm 6",
                                             output_type=pytesseract.Output.DICT)

        words = []
        count = len(data.get("text", []))
        for index in range(count):
            text = str(data["text"][index] or "").strip()
            if not text:
                continue
            left = int(data["left"][index])
            top = int(data["top"][index])
            height = int(data["height"][index])
            words.append((int((top + height / 2) / scale), left, text))

        line_groups = []
        for y, left, text in sorted(words):
            group = next((item for item in line_groups if abs(item["y"] - y) <= 6), None)
            if group is None:
                group = {"y": y, "words": []}
                line_groups.append(group)
            group["words"].append((left, text))

        return [(group["y"], " ".join(text for _, text in sorted(group["words"])))
                for group in sorted(line_groups, key=lambda item: item["y"])
                ]

    @classmethod
    def parse_lines(cls, lines: list[tuple[int, str]]) -> RatingTableSnapshot:
        rows = []
        for y, text in lines:
            normalized = cls._normalize(text)
            has_date = bool(re.search(r"\b\d{2}\.\d{2}\.\d{4}\b", text))
            looks_like_header = (not has_date and (re.match(r"\s*(?:n|№)\b", text, flags=re.IGNORECASE)
                                                   or ("вид" in normalized and ("оценка" in normalized or "водителя" in normalized))))
            if looks_like_header:
                continue

            scored = [(cls._kind_score(kind, text), kind) for kind in KNOWN_RATING_KINDS]
            score, kind = max(scored, default=(0.0, ""))
            hours_match = re.search(r"(?<!\d)(\d{1,3})\s*(?:ч|4)\s*\.?", text, flags=re.IGNORECASE)
            hours = int(hours_match.group(1)) if hours_match else 0

            if score < 0.62:
                looks_like_data_row = bool(has_date
                                           or re.match(r"\s*\d+\s+", text))
                if not looks_like_data_row:
                    continue
                if hours == 0:
                    continue
                kind = "__unknown__"

            rows.append(RatingRow(kind=kind, hours=hours, y=int(y), text=text))

        recognized = "\n".join(text for _, text in lines)
        return RatingTableSnapshot(rows=tuple(rows), recognized_text=recognized)

    def read(self, path: str | Path) -> RatingTableSnapshot:
        return self.parse_lines(self.line_reader(path))
