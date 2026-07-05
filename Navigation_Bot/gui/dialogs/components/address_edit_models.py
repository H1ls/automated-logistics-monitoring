from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class AddressPointDraft:
    address: str = ""
    date: str = ""
    time: str = ""


class AddressBlocksCodec:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self._point_pattern = re.compile(rf"^{re.escape(prefix)}\s+(\d+)$")

    def parse(self, blocks: list | None) -> tuple[list[AddressPointDraft], str]:
        numbered_points: list[tuple[int, AddressPointDraft]] = []
        comments: list[str] = []

        for block in blocks or []:
            if not isinstance(block, dict):
                continue
            sequence = self.sequence_from_block(block)
            if sequence is not None:
                numbered_points.append((sequence, AddressPointDraft(
                    address=str(block.get(f"{self.prefix} {sequence}") or "").strip(),
                    date=self._clean_optional(block.get(f"Дата {sequence}")),
                    time=self._clean_optional(block.get(f"Время {sequence}")),
                )))
                continue

            comment = block.get("Комментарий", block.get(f"{self.prefix} другое", ""))
            if comment:
                comments.append(str(comment).strip())

        numbered_points.sort(key=lambda item: item[0])
        return [point for _, point in numbered_points], "\n".join(filter(None, comments))

    def serialize(self, points: list[AddressPointDraft], comment: str = "") -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        sequence = 1
        for point in points:
            address = (point.address or "").strip()
            if not address:
                continue
            result.append({f"{self.prefix} {sequence}": address,
                           f"Дата {sequence}": (point.date or "").strip() or "Не указано",
                           f"Время {sequence}": (point.time or "").strip() or "Не указано",
                           })
            sequence += 1

        normalized_comment = (comment or "").strip()
        if normalized_comment:
            result.append({"Комментарий": normalized_comment})
        return result

    def sequence_from_block(self, block: dict) -> int | None:
        for key in block:
            match = self._point_pattern.match(str(key).strip())
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _clean_optional(value) -> str:
        text = str(value or "").strip()
        return "" if text == "Не указано" else text
