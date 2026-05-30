from PyQt6.QtCore import QTimer, Qt
from datetime import datetime, timedelta, timezone
from PyQt6.QtGui import QColor, QBrush


class RowHighlighter:
    def __init__(self, table, task_repository, log, hours_default=2):
        self.table = table
        self.task_repository = task_repository
        self.log = log
        self.hours_default = hours_default
        self.duration_minutes = hours_default * 60
        self.until_map = {}
        self.key_to_visual = None  # callable: key -> visual_row

        # Colors used by this highlighter (keep in one place)
        self._row_manual_brush = QBrush(QColor("#e9f2d3"))  # light green
        self._unload_expired_brush = QBrush(QColor("#FFD6D6"))  # light red (cell only)

    def apply_settings(self, settings: dict):
        highlight = settings.get("highlight", {}) or {}

        minutes = highlight.get("duration_minutes", self.duration_minutes)

        try:
            self.duration_minutes = max(1, int(minutes))
        except Exception:
            self.duration_minutes = 120  # fallback 2 часа

    def clear_all_highlight_until(self):
        data = self.task_repository.get() or []
        changed = False

        for row in data:
            if isinstance(row, dict) and "highlight_until" in row:
                row.pop("highlight_until", None)
                changed = True

        self.until_map.clear()

        if changed:
            self.task_repository.save()

        return changed

    def toggle_highlight(self, index_key: int):
        data = self.task_repository.get() or []

        rec = None
        for r in data:
            if r.get("index") == index_key:
                rec = r
                break

        if not rec:
            self.log(f"⚠️ toggle_highlight: не найдена запись index={index_key}")
            return False

        # если уже есть → убрать
        if rec.get("highlight_until"):
            rec.pop("highlight_until", None)
            self.until_map.pop(index_key, None)

            # снять подсветку
            if callable(self.key_to_visual):
                visual_row = self.key_to_visual(index_key)
                if 0 <= visual_row < self.table.rowCount():
                    self._paint_row(visual_row, enabled=False)

            self.task_repository.save()
            return False  # выключили

        # если нет → включить
        self.highlight_for(index_key)
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

    def highlight_for(self, index_key: int, hours: int | None = None):
        """
        Подсветить запись (и строку в таблице) по стабильному ключу index_key.
        Хранит highlight_until в самой записи JSON (rec["highlight_until"]).
        ВАЖНО: highlight_until трактуется как "время постановки на слежение".
        until_map хранит key -> expiry datetime (когда нужно снять подсветку).
        """
        if index_key is None:
            self.log("⚠️ highlight_for: index_key=None")
            return

        minutes = self.duration_minutes if hours is None else int(hours * 60)
        started_at = datetime.now()
        started_iso = started_at.strftime("%Y-%m-%d %H:%M:%S")
        expiry_dt = started_at + timedelta(minutes=minutes)

        data = self.task_repository.get() or []

        # найти запись по ключу
        rec = None
        for r in data:
            if r.get("index") == index_key:
                rec = r
                break

        if rec is None:
            self.log(f"⚠️ highlight_for: запись index={index_key} не найдена")
            return

        # сохранить в JSON запись
        rec["highlight_until"] = started_iso
        self.task_repository.save()

        # сохранить в runtime-map
        self.until_map[index_key] = expiry_dt

        # покрасить строку на экране (через mapper key->visual_row)
        visual_row = -1
        if callable(self.key_to_visual):
            try:
                visual_row = self.key_to_visual(index_key)
            except Exception as e:
                self.log(f"⚠️ key_to_visual mapper error: {e}")
                visual_row = -1

        if 0 <= visual_row < self.table.rowCount():
            self._paint_row(visual_row, enabled=True)

        # поставить таймер на авто-снятие (если к тому моменту истечёт)
        QTimer.singleShot(minutes * 60 * 1000, lambda: self._clear_if_expired(index_key))

    def reapply_from_json(self):
        """
        Вызывается после перерисовки таблицы (after_display).
        Смотрит highlight_until в каждой записи и заново красит строки
        по ключу index (через mapper key->visual_row).
        """
        data = self.task_repository.get() or []
        now = datetime.now()

        self.until_map.clear()

        for rec in data:
            index_key = rec.get("index")
            iso = (rec.get("highlight_until") or "").strip()
            if index_key is None or not iso:
                continue

            try:
                started_at = datetime.strptime(iso, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            expiry_dt = started_at + timedelta(minutes=self.duration_minutes)
            if now >= expiry_dt:
                continue

            # сохраняем в runtime-map: key -> datetime
            self.until_map[index_key] = expiry_dt

            # красим строку по текущей позиции (через mapper)
            if callable(self.key_to_visual):
                try:
                    visual_row = self.key_to_visual(index_key)
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
            QTimer.singleShot(remaining_ms, lambda k=index_key: self._clear_if_expired(k))

    def _clear_if_expired(self, index_key: int):
        expiry_dt = self.until_map.get(index_key)
        if not expiry_dt:
            return

        if datetime.now() < expiry_dt:
            return  # ещё не истекло

        data = self.task_repository.get() or []

        rec = None
        for r in data:
            if r.get("index") == index_key:
                rec = r
                break
        if rec is None:
            self.until_map.pop(index_key, None)
            return

        # очистить JSON-метку
        if rec.get("highlight_until"):
            rec["highlight_until"] = ""
            self.task_repository.save()

        self.until_map.pop(index_key, None)

        # снять подсветку с текущей строки на экране
        visual_row = -1
        if callable(self.key_to_visual):
            try:
                visual_row = self.key_to_visual(index_key)
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

    def highlight_expired_unloads(self):
        """
        Подсвечивает ячейку выгрузки КРАСНЫМ, если время первой НЕобработанной выгрузки меньше текущего.
        Подсветка НЕ сохраняется в JSON (её можно пересчитать при перерисовке).
        """

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
            index_key = rec.get("index")
            if index_key is None or not callable(self.key_to_visual):
                continue

            try:
                visual_row = self.key_to_visual(index_key)
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

                    if dt_unload < now:
                        item = self.table.item(visual_row, 5)
                        if item:
                            item.setBackground(self._unload_expired_brush)
                        break
                except Exception:
                    continue
