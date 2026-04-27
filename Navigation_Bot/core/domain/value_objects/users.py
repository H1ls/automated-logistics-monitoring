from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

@dataclass(slots=True)
class Users:
    id: Optional[int] = None
    username:str = ""
    full_name: str = ""
    role: str = ""
    is_active: bool = True
    created_at: str = ""
