# LogistX/onec/steps/capture_race_ui.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass
class UiPoint:
    name: str
    x: int
    y: int
    score: float | None = None
    source: str = "unknown"


class CaptureRaceUiStep:
    stage = "capture_race_ui"

    REQUIRED_POINTS = ("start_page_tab",
                       "race_params_tab",
                       "driver_rating_tab",
                       "cargo_tab",
                       "departure_label",
                       "departure_date_field",
                       "departure_time_field",)

    def __init__(self, session, errors, log_func=print, persist_min_score: float = 0.90):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.persist_min_score = float(persist_min_score)

    def _put_ctx(self, ctx, point: UiPoint):
        ctx.state.setdefault("ui_points", {})
        ctx.state["ui_points"][point.name] = {"x": point.x,
                                              "y": point.y,
                                              "score": point.score,
                                              "source": point.source,}

    def _store_anchor(self, point: UiPoint):
        self.session.ui_map.set_anchor(point.name, point.x, point.y)

    def _log_point(self, point: UiPoint):
        score_part = f", score={point.score:.3f}" if point.score is not None else ""
        self.log(f"📍 {point.name}: ({point.x}, {point.y}), source={point.source}{score_part}")

    def _load_from_uimap_to_ctx(self, ctx):
        self.log("♻️ UI уже откалиброван — беру координаты из onec_ui_map.json")
        for name in self.REQUIRED_POINTS:
            anchor = self.session.ui_map.get_optional_anchor(name)
            if not anchor:
                raise RuntimeError(f"В ui_map отсутствует anchor '{name}'")
            x, y = anchor
            self._put_ctx(ctx, UiPoint(name=name, x=x, y=y, source="ui_map"))

    def _find_on_shot(self, shot_path, template_name: str, point_name: str) -> UiPoint | None:
        m = self.session.find_template_on_shot(shot_path, template_name)
        if not m:
            return None
        return UiPoint(name=point_name,
                       x=int(m.center[0]),
                       y=int(m.center[1]),
                       score=float(m.score),
                       source=f"template:{template_name}", )

    def _resolve_departure_label(self, shot_path) -> UiPoint | None:
        # support both json keys: departure_label / lbl_departure
        for template_name in ("departure_label", "lbl_departure"):
            if not self.session.ui_map.get_optional_template(template_name):
                continue
            point = self._find_on_shot(shot_path, template_name, "departure_label")
            if point:
                return point

        anchor = self.session.ui_map.get_optional_anchor("departure_label")
        if anchor:
            return UiPoint(name="departure_label",
                           x=anchor[0],
                           y=anchor[1],
                           score=None,
                           source="anchor", )
        return None

    def _build_field_from_label(self, field_name: str, label_point: UiPoint) -> UiPoint | None:
        offset = self.session.ui_map.get_optional_offset(f"{field_name}_from_departure_label")
        if offset:
            dx, dy = offset
            return UiPoint(name=field_name,
                           x=label_point.x + dx,
                           y=label_point.y + dy,
                           score=label_point.score,
                           source=f"offset_from_departure_label({dx},{dy})", )

        anchor = self.session.ui_map.get_optional_anchor(field_name)
        if anchor:
            return UiPoint(name=field_name,
                           x=anchor[0],
                           y=anchor[1],
                           score=None,
                           source="anchor", )
        return None

    def _points_are_confident(self, points: list[UiPoint]) -> bool:
        for p in points:
            if p.score is None:
                return False
            if p.score < self.persist_min_score:
                return False
        return True

    def _save_debug_overlay(self, shot_path: Path, points: list[UiPoint]):
        try:
            debug_path = self.session.tmp_dir / "race_form_calibration_debug.png"
            with Image.open(shot_path).convert("RGB") as img:
                draw = ImageDraw.Draw(img)
                r = 8
                for p in points:
                    draw.ellipse((p.x - r, p.y - r, p.x + r, p.y + r), outline="red", width=3)
                    draw.text((p.x + 10, p.y - 10), p.name, fill="red")
                img.save(debug_path)
            self.log(f"🖼 debug overlay сохранён: {debug_path}")
        except Exception as e:
            self.log(f"⚠️ Не удалось сохранить debug overlay: {e}")

    def run(self, ctx):
        if self.session.ui_calibrated:
            self._load_from_uimap_to_ctx(ctx)
            return

        self.log("🧭 Первый рейс после запуска — one-shot калибровка по одному скрину")

        shot_path = self.session.capture_current_race_form("race_form_calibration.png")
        self.log(f"📸 Снимок формы: {shot_path}")

        found: list[UiPoint] = []

        stable_templates = [("start_page_tab", "start_page_tab"),
                            ("race_params_tab", "race_params_tab"),
                            ("driver_rating_tab", "driver_rating_tab"), ]

        for template_name, point_name in stable_templates:
            point = self._find_on_shot(shot_path, template_name, point_name)
            if not point:
                raise RuntimeError(f"Не удалось найти '{point_name}' на общем скрине формы")
            found.append(point)
        start_page = next(p for p in found if p.name == "start_page_tab")

        offset = self.session.ui_map.get_offset("cargo_tab_from_start_page_tab")

        cargo_tab = UiPoint(name="cargo_tab",
                            x=start_page.x + offset[0],
                            y=start_page.y + offset[1],
                            score=start_page.score,
                            source=f"offset_from_start_page_tab({offset[0]},{offset[1]})", )

        found.append(cargo_tab)
        departure_label = self._resolve_departure_label(shot_path)
        if not departure_label:
            raise RuntimeError("Не удалось найти 'Отправлен' (lbl_departure)")
        found.append(departure_label)

        departure_date = self._build_field_from_label("departure_date_field", departure_label)
        if not departure_date:
            raise RuntimeError("Не удалось вычислить поле даты отправления")
        found.append(departure_date)

        departure_time = self._build_field_from_label("departure_time_field", departure_label)
        if not departure_time:
            raise RuntimeError("Не удалось вычислить поле времени отправления")
        found.append(departure_time)

        for point in found:
            self._put_ctx(ctx, point)
            self._log_point(point)

        self._save_debug_overlay(Path(shot_path), found)

        template_points = [p for p in found if p.source.startswith("template:")]
        if template_points and self._points_are_confident(template_points):
            self.log("💾 Все стабильные точки найдены уверенно — сохраняю в onec_ui_map.json")
            for point in found:
                self._store_anchor(point)
            self.session.ui_map.save()
        else:
            self.log("ℹ️ Не все точки найдены достаточно уверенно — сохраняю только в ctx.state")

        self.session.ui_calibrated = True
