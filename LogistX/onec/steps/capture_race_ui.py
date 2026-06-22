from __future__ import annotations

from dataclasses import dataclass

from LogistX.onec.artifacts import OneCArtifacts


@dataclass
class UiPoint:
    name: str
    x: int
    y: int
    score: float | None = None
    source: str = "unknown"


class CaptureRaceUiStep:
    stage = "capture_race_ui"

    REQUIRED_POINTS = (
        "start_page_tab",
        "race_params_tab",
        "driver_rating_tab",
        "cargo_tab",
        "departure_label",
        "departure_date_field",
        "departure_time_field",
        "wait_load",
    )

    STABLE_TEMPLATES = (
        ("start_page_tab", "start_page_tab"),
        ("race_params_tab", "race_params_tab"),
        ("driver_rating_tab", "driver_rating_tab"),
        ("wait_load", "wait_load"),
    )

    def __init__(self, session, errors, log_func=print, persist_min_score: float = 0.90,
                 artifacts=None, find_attempts: int = 3):
        self.session = session
        self.errors = errors
        self.log = log_func
        self.persist_min_score = float(persist_min_score)
        self.artifacts = artifacts or getattr(session, "artifacts", None) or OneCArtifacts(session, log_func=log_func)
        self.find_attempts = max(1, int(find_attempts))

    def _put_ctx(self, ctx, point: UiPoint):
        ctx.state.setdefault("ui_points", {})
        ctx.state["ui_points"][point.name] = {"x": point.x,
                                              "y": point.y,
                                              "score": point.score,
                                              "source": point.source,
                                              }

    def _store_anchor(self, point: UiPoint):
        self.session.ui_map.set_anchor(point.name, point.x, point.y)

    def _load_from_uimap_to_ctx(self, ctx, shot_path=None):
        self.log("♻️ UI уже откалиброван - беру координаты из onec_ui_map.json")
        missing_template_points: list[str] = []

        for name in self.REQUIRED_POINTS:
            anchor = self.session.ui_map.get_optional_anchor(name)
            if anchor:
                x, y = anchor
                self._put_ctx(ctx, UiPoint(name=name, x=x, y=y, source="ui_map"))
                continue

            if self.session.ui_map.get_optional_template(name):
                missing_template_points.append(name)
                continue

            raise RuntimeError(f"В ui_map отсутствует anchor '{name}'")

        if missing_template_points:
            self._load_missing_template_points(ctx, missing_template_points, shot_path=shot_path)

    def _load_missing_template_points(self, ctx, point_names: list[str], shot_path=None):
        shot_path = shot_path or self.artifacts.capture_full(self.stage, "calibration_missing")
        should_save = False

        for name in point_names:
            point = self._find_with_retries(shot_path, name, name)
            if not point:
                raise RuntimeError(
                    f"В ui_map отсутствует anchor '{name}' и template "
                    f"не найден за {self.find_attempts} попытки"
                )

            self._put_ctx(ctx, point)
            if point.score is not None and point.score >= self.persist_min_score:
                self._store_anchor(point)
                should_save = True

        if should_save:
            self.session.ui_map.save()

    def _find_on_shot(self, shot_path, template_name: str, point_name: str) -> UiPoint | None:
        m = self.session.find_template_on_shot(shot_path, template_name)
        if not m:
            return None
        return UiPoint(
            name=point_name,
            x=int(m.center[0]),
            y=int(m.center[1]),
            score=float(m.score),
            source=f"template:{template_name}",
        )

    def _find_with_retries(self, initial_shot, template_name: str, point_name: str) -> UiPoint | None:
        shot_path = initial_shot
        for attempt in range(1, self.find_attempts + 1):
            point = self._find_on_shot(shot_path, template_name, point_name)
            if point:
                if attempt > 1:
                    self.log(f"✅ '{point_name}' найден с попытки {attempt}/{self.find_attempts}")
                return point

            if attempt < self.find_attempts:
                self.log(
                    f"⚠️ '{point_name}' не найден, новый скриншот "
                    f"и попытка {attempt + 1}/{self.find_attempts}"
                )
                self.session.sleep(0.35)
                shot_path = self.artifacts.capture_full(
                    self.stage, f"retry_{point_name}_{attempt + 1}"
                )
        return None

    def _resolve_departure_label(self, shot_path) -> UiPoint | None:
        for template_name in ("departure_label", "lbl_departure"):
            if not self.session.ui_map.get_optional_template(template_name):
                continue
            point = self._find_with_retries(shot_path, template_name, "departure_label")
            if point:
                return point

        anchor = self.session.ui_map.get_optional_anchor("departure_label")
        if anchor:
            return UiPoint(name="departure_label", x=anchor[0], y=anchor[1], source="anchor")
        return None

    def _build_field_from_label(self, field_name: str, label_point: UiPoint) -> UiPoint | None:
        offset = self.session.ui_map.get_optional_offset(f"{field_name}_from_departure_label")
        if offset:
            dx, dy = offset
            return UiPoint(
                name=field_name,
                x=label_point.x + dx,
                y=label_point.y + dy,
                score=label_point.score,
                source=f"offset_from_departure_label({dx},{dy})",
            )

        anchor = self.session.ui_map.get_optional_anchor(field_name)
        if anchor:
            return UiPoint(name=field_name, x=anchor[0], y=anchor[1], source="anchor")
        return None

    def _points_are_confident(self, points: list[UiPoint]) -> bool:
        return all(p.score is not None and p.score >= self.persist_min_score for p in points)

    def run(self, ctx):
        if self.session.ui_calibrated:
            self._load_from_uimap_to_ctx(ctx)
            return

        self.log("🧭 Первый рейс после запуска - one-shot калибровка по одному скрину")
        shot_path = self.artifacts.capture_full(self.stage, "calibration")

        found: list[UiPoint] = []
        for template_name, point_name in self.STABLE_TEMPLATES:
            point = self._find_with_retries(shot_path, template_name, point_name)
            if not point:
                raise RuntimeError(
                    f"Не удалось найти '{point_name}' "
                    f"за {self.find_attempts} попытки"
                )
            found.append(point)

        start_page = next(p for p in found if p.name == "start_page_tab")
        offset = self.session.ui_map.get_offset("cargo_tab_from_start_page_tab")
        found.append(
            UiPoint(
                name="cargo_tab",
                x=start_page.x + offset[0],
                y=start_page.y + offset[1],
                score=start_page.score,
                source=f"offset_from_start_page_tab({offset[0]},{offset[1]})",
            )
        )

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

        self.artifacts.annotate_points(shot_path, self.stage, "calibration_points",
                                       [(point.name, point.x, point.y) for point in found],
                                       )

        template_points = [p for p in found if p.source.startswith("template:")]
        if template_points and self._points_are_confident(template_points):
            self.log("💾 Все стабильные точки найдены уверенно - сохраняю в onec_ui_map.json")
            for point in found:
                self._store_anchor(point)
            self.session.ui_map.save()
        else:
            self.log("ℹ️ Не все точки найдены достаточно уверенно - сохраняю только в ctx.state")

        self.session.ui_calibrated = True
