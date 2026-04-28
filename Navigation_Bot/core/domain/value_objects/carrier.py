from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class Carrier:
    id: Optional[int] = None
    name: str = ""
    contact_person: str = ""
    phone: str = ""
    notes: str = ""
    is_active: bool = True
    created_at: str = ""