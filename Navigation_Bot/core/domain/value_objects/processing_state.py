from dataclasses import dataclass, field


@dataclass(slots=True)
class ProcessingState:
    processed_unloads: list[bool] = field(default_factory=list)

