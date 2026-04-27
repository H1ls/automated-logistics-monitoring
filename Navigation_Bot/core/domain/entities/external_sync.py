from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class ExternalSync:
    id: Optional[int] = None

    entity_type: str = ""      # "task", "vehicle", "race"
    entity_id: str = ""        # внутренний id / index / plate

    system_name: str = ""      # "google_sheets", "wialon", "1c"
    external_id: str = ""      # row_index, monitoring_id, race_no

    external_meta: dict = None

    last_sync_at: str = ""
    status: str = ""           # "ok", "error"
    error_message: str = ""