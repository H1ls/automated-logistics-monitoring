from dataclasses import dataclass, field

from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint


@dataclass(slots=True)
class RoutePlan:
    loads: list[RoutePoint] = field(default_factory=list)
    unloads: list[RoutePoint] = field(default_factory=list)


    def all_points(self) -> list[RoutePoint]:
        return [*self.loads, *self.unloads]

    def has_loads(self) -> bool:
        return bool(self.loads)

    def has_unloads(self) -> bool:
        return bool(self.unloads)