from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedUiPoint:
    name: str
    x: int
    y: int
    source: str


class UiPointResolver:
    """Согласованно определять координаты UI: контекст, сохранённый якорь, шаблон"""

    def __init__(self, session):
        self.session = session

    @staticmethod
    def _from_context(ctx, name: str) -> ResolvedUiPoint | None:
        if ctx is None:
            return None

        state = getattr(ctx, "state", {}) or {}
        points = state.get("ui_points") or {}
        value = points.get(name)
        if value is None:
            return None

        try:
            return ResolvedUiPoint(name=name,
                                   x=int(value["x"]),
                                   y=int(value["y"]),
                                   source="ctx.state"
                                   )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Некорректная UI-точка '{name}' в ctx.state: {value!r}") from exc

    def resolve(self, name: str, ctx=None) -> ResolvedUiPoint:
        point = self._from_context(ctx, name)
        if point:
            return point

        anchor = self.session.ui_map.get_optional_anchor(name)
        if anchor:
            return ResolvedUiPoint(name=name, x=int(anchor[0]), y=int(anchor[1]), source="ui_map.anchor")

        if self.session.ui_map.get_optional_template(name):
            match = self.session.find_template_global(name)
            if not match:
                raise RuntimeError(f"Не удалось найти UI-точку '{name}' по шаблону")
            return ResolvedUiPoint(name=name,
                                   x=int(match.center[0]),
                                   y=int(match.center[1]),
                                   source="ui_map.template",
                                   )

        raise RuntimeError(f"Не задана UI-точка '{name}' в ctx.state, anchors или templates")

    def click(self, name: str, ctx=None) -> ResolvedUiPoint:
        point = self.resolve(name, ctx=ctx)
        self.session.click(point.x, point.y)
        return point
