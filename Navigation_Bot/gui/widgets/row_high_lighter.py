from PyQt6.QtCore import QTimer
from datetime import datetime, timedelta, timezone
from PyQt6.QtGui import QColor, QBrush

from Navigation_Bot.core.domain.task_identity import row_identity_for_gui
from Navigation_Bot.core.logging import normalize_log_func


class RowHighlighter:
    def __init__(self, table, task_repository, log, hours_default=2):
        self.table = table
        self.task_repository = task_repository
        self.log = normalize_log_func(log)
        self.hours_default = hours_default
        self.duration_minutes = hours_default * 60
        self.expired_unload_grace_minutes = 0
        self.enabled_types = {"manual", "expired_unloads", "future_load"}
        self.until_map = {}
        self.key_to_visual = None  # callable: row_identity -> visual_row

        self._row_manual_brush = QBrush(QColor("#e9f2d3"))  # light green
        self._unload_expired_brush = QBrush(QColor("#FFD6D6"))  # light red (cell only)
        self._completed_row_brush = QBrush(QColor("#E6F4EA"))
        self._completed_text_brush = QBrush(QColor("#2F5D3A"))

    def apply_settings(self, settings: dict):
        highlight = settings.get("highlight", {}) or {}

        minutes = highlight.get("duration_minutes", self.duration_minutes)

        try:
            self.duration_minutes = max(1, int(minutes))
        except Exception:
            self.duration_minutes = 120  # fallback 2 часа

        try:
            self.expired_unload_grace_minutes = max(0, int(highlight.get("expired_unload_grace_minutes", 0)))
        except (TypeError, ValueError):
            self.expired_unload_grace_minutes = 0

        enabled_types = highlight.get("enabled_types")
        if isinstance(enabled_types, list):
            self.enabled_types = {str(v) for v in enabled_types}
        else:
            self.enabled_types = {"manual", "expired_unloads", "future_load"}

        if "manual" not in self.enabled_types:
            self.until_map.clear()

    def clear_all_highlight_until(self):
        data = self.task_repository.get() or []
        changed = False

        for row in data:
            if isinstance(row, dict) and "highlight_until" in row:
                row.pop("highlight_until", None)
                changed = True

        self.until_map.clear()

        if changed:
            self.task_repository.save(source="user")

        return changed

    def toggle_highlight(self, row_identity: int):
        if "manual" not in self.enabled_types:
            return False

        data = self.task_repository.get() or []

        rec = None
        for r in data:
            if row_identity_for_gui(r) == row_identity:
                rec = r
                break

        if not rec:
            self.log(f"⚠️ toggle_highlight: не найдена запись row_identity={row_identity}")
            return False

        # если уже есть → убрать
        if rec.get("highlight_until"):
            rec.pop("highlight_until", None)
            self.until_map.pop(row_identity, None)

            # снять подсветку
            if callable(self.key_to_visual):
                visual_row = self.key_to_visual(row_identity)
                if 0 <= visual_row < self.table.rowCount():
                    self._paint_row(visual_row, enabled=False)

            self.task_repository.save(source="user")
            return False  # выключили

        # если нет → включить на длительность из настроек
        self.highlight_for(row_identity)
        return True  # включили

    def set_view_order(self, view_order: list[int] | None):
        self.view_order = view_order
        self.real_to_visual = {}
        if not view_order:
            return
        for visual, real in enumerate(view_order):
            self.real_to_visual[real] = visual

    def set_key_to_visual_mapper(self, mapper):
        self.key_to_visual = mapper

    @staticmethod
    def _to_iso_utc(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _from_iso_utc(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    def highlight_for(self, row_identity: int, hours: int | None = None):
        """
        Подсветить запись (и строку в таблице) по стабильному ключу row_identity.
        Хранит highlight_until в самой записи JSON (rec["highlight_until"]).
        highlight_until трактуется как конкретное время окончания подсветки.
        until_map хранит key -> expiry datetime (когда нужно снять подсветку).
        """
        minutes = self.duration_minutes if hours is None else int(hours * 60)
        self._set_highlight_for_minutes(row_identity, minutes)

    def set_highlight_for(self, row_identity: int, hours: int):
        self._set_highlight_for_minutes(row_identity, int(hours * 60))

    def _set_highlight_for_minutes(self, row_identity: int, minutes: int):
        if "manual" not in self.enabled_types:
            return
        if row_identity is None:
            self.log("⚠️ highlight_for: row_identity=None")
            return

        minutes = max(1, int(minutes))
        expiry_dt = datetime.now() + timedelta(minutes=minutes)
        expiry_iso = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

        data = self.task_repository.get() or []

        # найти запись по ключу
        rec = None
        for r in data:
            if row_identity_for_gui(r) == row_identity:
                rec = r
                break

        if rec is None:
            self.log(f"⚠️ highlight_for: запись row_identity={row_identity} не найдена")
            return

        # сохранить в JSON запись
        rec["highlight_until"] = expiry_iso
        self.task_repository.save(source="user")

        # сохранить в runtime-map
        self.until_map[row_identity] = expiry_dt

        # покрасить строку на экране (через mapper key->visual_row)
        visual_row = -1
        if callable(self.key_to_visual):
            try:
                visual_row = self.key_to_visual(row_identity)
            except Exception as e:
                self.log(f"⚠️ key_to_visual mapper error: {e}")
                visual_row = -1

        if 0 <= visual_row < self.table.rowCount():
            self._paint_row(visual_row, enabled=True)

        # поставить таймер на авто-снятие (если к тому моменту истечёт)
        QTimer.singleShot(minutes * 60 * 1000, lambda: self._clear_if_expired(row_identity))

    def _parse_highlight_until(self, value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None

        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        try:
            parsed = self._from_iso_utc(text)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    def reapply_from_rows(self):
        """
        Вызывается после перерисовки таблицы (after_display).
        Смотрит highlight_until в каждой записи и заново красит строки
        по ключу row_identity (через mapper key->visual_row).
        """
        if "manual" not in self.enabled_types:
            self.until_map.clear()
            return

        data = self.task_repository.get() or []
        now = datetime.now()
        changed = False

        self.until_map.clear()

        for rec in data:
            row_identity = row_identity_for_gui(rec)
            iso = (rec.get("highlight_until") or "").strip()
            if row_identity is None or not iso:
                continue

            expiry_dt = self._parse_highlight_until(iso)
            if expiry_dt is None:
                continue

            if now >= expiry_dt:
                rec["highlight_until"] = ""
                changed = True
                continue

            # сохраняем в runtime-map: key -> datetime
            self.until_map[row_identity] = expiry_dt

            # красим строку по текущей позиции (через mapper)
            if callable(self.key_to_visual):
                try:
                    visual_row = self.key_to_visual(row_identity)
                except Exception as e:
                    self.log(f"⚠️ key_to_visual mapper error: {e}")
                    continue
            else:
                # если mapper не задан — мы не знаем, куда красить
                continue

            if 0 <= visual_row < self.table.rowCount():
                self._paint_row(visual_row, enabled=True)

            # авто-снятие после оставшегося времени
            remaining_ms = int(max(1, (expiry_dt - now).total_seconds() * 1000))
            QTimer.singleShot(remaining_ms, lambda k=row_identity: self._clear_if_expired(k))

        if changed:
            self.task_repository.save(source="user")

    def _clear_if_expired(self, row_identity: int):
        expiry_dt = self.until_map.get(row_identity)
        if not expiry_dt:
            return

        if datetime.now() < expiry_dt:
            return  # ещё не истекло

        data = self.task_repository.get() or []

        rec = None
        for r in data:
            if row_identity_for_gui(r) == row_identity:
                rec = r
                break
        if rec is None:
            self.until_map.pop(row_identity, None)
            return

        # очистить JSON-метку
        if rec.get("highlight_until"):
            rec["highlight_until"] = ""
            self.task_repository.save(source="user")

        self.until_map.pop(row_identity, None)

        # снять подсветку с текущей строки на экране
        visual_row = -1
        if callable(self.key_to_visual):
            try:
                visual_row = self.key_to_visual(row_identity)
            except Exception:
                visual_row = -1

        if 0 <= visual_row < self.table.rowCount():
            self._paint_row(visual_row, enabled=False)

    def _paint_row(self, row_idx: int, enabled: bool):

        default_brush = QBrush()

        for col in range(self.table.columnCount()):
            item = self.table.item(row_idx, col)
            if not item:
                continue

            # Если это колонка 'Выгрузка' и уже есть подсветка выгрузки - не трогаем.
            current_color = item.background().color().name()
            if col == 5 and current_color.lower() in ["#ffd6d6", "#ffcccc"]:
                continue

            item.setBackground(self._row_manual_brush if enabled else default_brush)

    def highlight_completed_rows(self):
        data = self.task_repository.get() or []

        for rec in data:
            if not self._is_inactive_task(rec):
                continue

            row_identity = row_identity_for_gui(rec)
            if row_identity is None or not callable(self.key_to_visual):
                continue

            try:
                visual_row = self.key_to_visual(row_identity)
            except Exception as e:
                self.log(f"key_to_visual mapper error: {e}")
                continue

            if 0 <= visual_row < self.table.rowCount():
                self._paint_completed_row(visual_row)

    @staticmethod
    def _is_inactive_task(rec: dict) -> bool:
        return str((rec or {}).get("status") or "").strip().lower() in {"completed", "archived", "cancelled"}

    def _paint_completed_row(self, row_idx: int):
        for col in range(self.table.columnCount()):
            item = self.table.item(row_idx, col)
            if not item:
                continue
            item.setBackground(self._completed_row_brush)
            item.setForeground(self._completed_text_brush)

    def highlight_expired_unloads(self):
        """
        Подсвечивает ячейку выгрузки КРАСНЫМ, если время первой НЕобработанной выгрузки меньше текущего.
        Подсветка НЕ сохраняется в JSON (её можно пересчитать при перерисовке).
        """
        if "expired_unloads" not in self.enabled_types:
            return

        data = self.task_repository.get() or []
        now = datetime.now()

        for real_idx, rec in enumerate(data):
            unloads_all = rec.get("Выгрузка", [])
            processed = rec.get("processed", [])

            if not unloads_all or not isinstance(unloads_all, list):
                continue

            # как в TableManager: берём только точки (без Комментарий / "Выгрузка другое")
            points = []
            for d in unloads_all:
                if not isinstance(d, dict):
                    continue
                if "Комментарий" in d:
                    continue
                if "Выгрузка другое" in d:
                    continue
                if any(k.startswith("Выгрузка ") for k in d.keys()):
                    points.append(d)

            if not points:
                continue

            #  real -> visual (если сортировка включена)
            row_identity = row_identity_for_gui(rec)
            if row_identity is None or not callable(self.key_to_visual):
                continue

            try:
                visual_row = self.key_to_visual(row_identity)
            except Exception as e:
                self.log(f"⚠️ key_to_visual mapper error: {e}")
                continue

            # первая НЕ обработанная точка
            for i, unload in enumerate(points, start=1):
                is_done = processed[i - 1] if (i - 1) < len(processed) else False
                if is_done:
                    continue

                date_str = unload.get(f"Дата {i}", "")
                time_str = unload.get(f"Время {i}", "")
                if not date_str or not time_str:
                    continue

                try:
                    if time_str.count(":") == 1:
                        time_str += ":00"
                    dt_unload = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")

                    if dt_unload + timedelta(minutes=self.expired_unload_grace_minutes) < now:
                        item = self.table.item(visual_row, 5)
                        if item:
                            item.setBackground(self._unload_expired_brush)
                        break
                except Exception:
                    continue

    def highlight_expired_unloads(self):
        if "expired_unloads" not in self.enabled_types:
            return

        data = self.task_repository.get() or []
        now = datetime.now()

        for rec in data:
            if self._is_inactive_task(rec):
                continue

            points = self._highlight_unload_points(rec)
            if not points:
                continue

            row_identity = row_identity_for_gui(rec)
            if row_identity is None or not callable(self.key_to_visual):
                continue

            try:
                visual_row = self.key_to_visual(row_identity)
            except Exception as e:
                self.log(f"key_to_visual mapper error: {e}")
                continue

            for unload in points:
                if unload.get("processed"):
                    continue

                date_str = str(unload.get("date") or "")
                time_str = str(unload.get("time") or "")
                if not date_str or not time_str:
                    continue

                try:
                    if time_str.count(":") == 1:
                        time_str += ":00"
                    dt_unload = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
                except Exception:
                    continue

                if dt_unload + timedelta(minutes=self.expired_unload_grace_minutes) < now:
                    item = self.table.item(visual_row, 5)
                    if item:
                        item.setBackground(self._unload_expired_brush)
                    break

    def _highlight_unload_points(self, rec: dict) -> list[dict]:
        unloads = rec.get("unloads")
        if isinstance(unloads, list):
            processed = rec.get("processed_unloads")
            if not isinstance(processed, list):
                processed = rec.get("processed", [])

            points = []
            for index, item in enumerate(unloads):
                if not isinstance(item, dict) or not item.get("address"):
                    continue
                points.append(
                    {
                        "date": item.get("date") or "",
                        "time": item.get("time") or "",
                        "processed": processed[index] if index < len(processed) else False,
                    }
                )
            if points:
                return points

        legacy_unloads = rec.get("Выгрузка", [])
        processed = rec.get("processed", [])
        if not isinstance(legacy_unloads, list):
            return []

        points = []
        for item in legacy_unloads:
            if not isinstance(item, dict):
                continue
            if "Комментарий" in item or "Выгрузка другое" in item:
                continue

            unload_keys = [key for key in item.keys() if key.startswith("Выгрузка ")]
            if not unload_keys:
                continue

            try:
                index = int(unload_keys[0].rsplit(" ", 1)[1])
            except (TypeError, ValueError, IndexError):
                index = len(points) + 1

            points.append(
                {
                    "date": item.get(f"Дата {index}") or "",
                    "time": item.get(f"Время {index}") or "",
                    "processed": processed[index - 1] if index - 1 < len(processed) else False,
                }
            )

        return points
