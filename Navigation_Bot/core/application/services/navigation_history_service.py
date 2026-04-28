from __future__ import annotations

from Navigation_Bot.core.application.services.json_history_service import JsonHistoryService
from Navigation_Bot.core.domain.entities.navigation_snapshot import NavigationSnapshot


class NavigationHistoryService(JsonHistoryService):
    def __init__(self, filepath: str, log=None):
        super().__init__(filepath=filepath,
                         time_field="collected_at",
                         log=log, )

    def append_snapshot(self, snapshot: NavigationSnapshot) -> None:
        self.append(snapshot)
