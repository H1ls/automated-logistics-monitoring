from dataclasses import dataclass, field


@dataclass(slots=True)
class ProcessingState:
    processed_unloads: list[bool] = field(default_factory=list)

    def ensure_size(self, unload_count: int) -> None:
        if unload_count < 0:
            unload_count = 0
        self.processed_unloads = (self.processed_unloads + [False] * unload_count)[:unload_count]

    def is_unload_processed(self, index: int) -> bool:
        if index < 0:
            return False
        if index >= len(self.processed_unloads):
            return False
        return self.processed_unloads[index]

    def mark_unload_processed(self, index: int) -> None:
        if index < 0:
            return
        if index >= len(self.processed_unloads):
            self.processed_unloads.extend([False] * (index + 1 - len(self.processed_unloads)))
        self.processed_unloads[index] = True
