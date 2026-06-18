from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class Note:
    id: Optional[int] = None

    trip_number: int = 0

    created_at: str = ""
    author: str = ""

    text: str = ""

    # media
    media_paths: list[str] = field(default_factory=list)
    media_type: str = ""  # "", "photo", "video", "mixed"

    is_important: bool = False
