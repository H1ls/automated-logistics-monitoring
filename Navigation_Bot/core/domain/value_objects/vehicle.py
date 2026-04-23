from dataclasses import dataclass


@dataclass(slots=True)
class Vehicle:
    plate_number: str
    monitoring_id: int | None = None