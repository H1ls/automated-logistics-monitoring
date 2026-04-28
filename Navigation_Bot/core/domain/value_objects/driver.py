from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

@dataclass(slots=True)
class Driver:
    id: Optional[int] = None
    full_name: str = ""
    phone: str = ""
    notes: str = ""
    is_active: bool = True
    carrier_id: Optional[int] = None
    created_at: str = ""