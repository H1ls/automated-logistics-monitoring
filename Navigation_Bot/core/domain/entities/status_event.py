from dataclasses import dataclass
from typing import Optional

"""
    История изменений статуса
    машина приехала → "гео": "в пути" → "у выгрузки"
    отметка выгрузки → "processed[2]"
"""

@dataclass(slots=True)
class StatusEvent:
    id: Optional[int] = None

    trip_number: int = 0

    event_type: str = ""     # "created", "updated", "unload_done", "closed"

    field_name: str = ""     # например "гео", "processed", "status"
    old_value: str = ""
    new_value: str = ""

    message: str = ""

    created_at: str = ""
    source: str = "user"     # "user", "google", "cleaner", "maps"
