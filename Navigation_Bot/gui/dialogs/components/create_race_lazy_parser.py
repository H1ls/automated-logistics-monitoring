from __future__ import annotations

import re
from typing import Any, Callable

from Navigation_Bot.bots.route_info_parser import RouteInfoParser


class CreateRaceLazyParser:
    def __init__(self, task_repository: Any, log: Callable[[str], None] | None = None):
        self.task_repository = task_repository
        self.log = log or (lambda _msg: None)
        self.route_parser = RouteInfoParser()

    def apply_if_needed(self, lazy_text: str, buffer: dict[str, Any]) -> dict[str, Any]:
        lazy_text = str(lazy_text or "").strip()
        if not lazy_text:
            return buffer
        if buffer.get("Погрузка") or buffer.get("Выгрузка"):
            return buffer

        load_text, unload_text = self.split_route_text(lazy_text)
        if not load_text or not unload_text:
            self.log("[DEBUG] Лентяй: не удалось разделить текст на погрузку/выгрузку")
            return buffer

        load_blocks = self.route_parser.parse(load_text, "Погрузка")
        unload_blocks = self.route_parser.parse(unload_text, "Выгрузка")
        if not load_blocks or not unload_blocks:
            self.log("[DEBUG] Лентяй: data_cleaner не вернул погрузку или выгрузку")
            return buffer

        buffer["Погрузка"] = load_blocks
        buffer["Выгрузка"] = unload_blocks
        buffer["raw_load"] = load_text
        buffer["raw_unload"] = unload_text
        buffer["comm_load"] = self.blocks_comment(load_blocks)
        buffer["comm_unload"] = self.blocks_comment(unload_blocks)
        return buffer

    @staticmethod
    def split_route_text(text: str) -> tuple[str, str]:
        normalized = str(text or "").replace("\r", "\n").strip()
        unload_match = re.search(r"\b(?:Разгрузка|Выгрузка)\s*:?", normalized, flags=re.IGNORECASE)
        if not unload_match:
            return normalized, ""

        load_text = normalized[:unload_match.start()].strip(" \n\t|")
        unload_text = normalized[unload_match.start():].strip(" \n\t|")

        load_match = re.search(r"\b(?:Загрузка|Погрузка)\s*:?", load_text, flags=re.IGNORECASE)
        if load_match:
            load_text = load_text[load_match.start():].strip(" \n\t|")

        return load_text, unload_text

    @staticmethod
    def blocks_comment(blocks: list[dict[str, str]]) -> str:
        comments = []
        for block in blocks:
            if isinstance(block, dict) and block.get("Комментарий"):
                comments.append(str(block.get("Комментарий") or "").strip())
        return "\n".join(comment for comment in comments if comment)
