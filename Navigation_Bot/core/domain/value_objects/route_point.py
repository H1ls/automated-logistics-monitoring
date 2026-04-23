from dataclasses import dataclass


@dataclass(slots=True)
class RoutePoint:
    kind: str              # "load" или "unload"
    sequence: int          # 1, 2, 3...
    address: str
    date: str = ""
    time: str = ""
    comment: str = ""