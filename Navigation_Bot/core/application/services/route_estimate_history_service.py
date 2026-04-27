from __future__ import annotations

from Navigation_Bot.core.application.services.json_history_service import JsonHistoryService
from Navigation_Bot.core.domain.entities.route_estimate import RouteEstimate


class RouteEstimateHistoryService(JsonHistoryService):
    def __init__(self, filepath: str, log=None):
        super().__init__(filepath=filepath,
                         time_field="calculated_at",
                         log=log, )

    def append_estimate(self, estimate: RouteEstimate) -> None:
        self.append(estimate)
