from dataclasses import dataclass, field

from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint


@dataclass(slots=True)
class RoutePlan:
    loads: list[RoutePoint] = field(default_factory=list)
    unloads: list[RoutePoint] = field(default_factory=list)