from __future__ import annotations

from dataclasses import dataclass


def normalize_pin_text(value: str) -> str:
    return (value or "").strip().upper().replace(" ", "")


@dataclass
class PinRow:
    card: str = ""
    pin: str = ""
    ts: str = ""
    supplier: str = ""

    @property
    def n_card(self) -> str:
        return normalize_pin_text(self.card)

    @property
    def n_ts(self) -> str:
        return normalize_pin_text(self.ts)
