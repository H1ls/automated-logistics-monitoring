from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

@dataclass(slots=True)
class Vehicle:
    id: Optional[int] = None  # внутренний id CRM
    plate_number: str = "" # номер машины
    monitoring_id: Optional[int] = None # id из Wialon
    carrier_id: Optional[int] = None
    created_at: str = ""
    brand: str = ""
    model: str = ""
    is_active: bool = True