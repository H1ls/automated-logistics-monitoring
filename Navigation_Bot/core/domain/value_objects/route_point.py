from dataclasses import dataclass


@dataclass(slots=True)
class RoutePoint:
    kind: str              # "load" или "unload"
    sequence: int          # 1, 2, 3...
    address: str
    date: str = ""
    time: str = ""
    comment: str = ""

    def is_load(self) -> bool:
        return self.kind == "load"

    def is_unload(self) -> bool:
        return self.kind == "unload"

    def planned_datetime_text(self) -> str:
        if self.date and self.time:
            return f"{self.date} {self.time}"
        if self.date:
            return self.date
        if self.time:
            return self.time
        return ""
