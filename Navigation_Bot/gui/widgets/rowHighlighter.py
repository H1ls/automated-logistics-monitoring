from PyQt6.QtCore import QTimer, Qt
from datetime import datetime, timedelta, timezone
from PyQt6.QtGui import QColor, QBrush

class RowHighlighter:
    def __init__(self, table, data_context, log, hours_default=2):
        self.table = table
        self.data_context = data_context
        self.log = log
        self.hours_default = hours_default
        self.until_map = {}  # row_idx -> datetime(UTC)
        self.key_to_visual = None  # callable: key -> visual_row

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

    from datetime import datetime, timedelta

    def highlight_for(self, index_key: int, hours: int | None = None):
        """
        Подсветить запись (и строку в таблице) по стабильному ключу index_key.
        Хранит highlight_until в самой записи JSON (rec["highlight_until"]).
        until_map хранит key -> datetime.
        """
        if index_key is None:
            self.log("⚠️ highlight_for: index_key=None")
            return

        hours = hours if hours is not None else self.hours_default
        until_dt = datetime.now() + timedelta(hours=hours)
        until_iso = until_dt.strftime("%Y-%m-%d %H:%M:%S")

        data = self.data_context.get() or []

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
        rec["highlight_until"] = until_iso
        self.data_context.save()

        # сохранить в runtime-map
        self.until_map[index_key] = until_dt

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
        QTimer.singleShot(hours * 60 * 60 * 1000, lambda: self._clear_if_expired(index_key))

    from datetime import datetime

    def reapply_from_json(self):
        """
        Вызывается после перерисовки таблицы (after_display).
        Смотрит highlight_until в каждой записи и заново красит строки
        по ключу index (через mapper key->visual_row).
        """
        data = self.data_context.get() or []
        now = datetime.now()

        self.until_map.clear()

        for rec in data:
            index_key = rec.get("index")
            iso = (rec.get("highlight_until") or "").strip()
            if index_key is None or not iso:
                continue

            try:
                until_dt = datetime.strptime(iso, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if now >= until_dt:
                continue

            # сохраняем в runtime-map: key -> datetime
            self.until_map[index_key] = until_dt

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
            # self.log(f"DEBUG paint key={index_key} -> row={visual_row}")

    def _clear_if_expired(self, index_key: int):
        until_dt = self.until_map.get(index_key)
        if not until_dt:
            return

        if datetime.now() < until_dt:
            return  # ещё не истекло

        data = self.data_context.get() or []

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
            self.data_context.save()

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
        green_brush = QBrush(QColor("#e9f2d3"))

        for col in range(self.table.columnCount()):
            item = self.table.item(row_idx, col)
            if not item:
                continue

            #  Если это колонка 'Выгрузка' и уже есть красная подсветка - не трогаем
            current_color = item.background().color().name()
            if col == 5 and current_color.lower() in ["#ffd6d6", "#ffcccc"]:
                continue

            item.setBackground(green_brush if enabled else default_brush)

    def highlight_expired_unloads(self):
        """Подсвечивает первую непройденную выгрузку, если её время уже меньше текущего."""


        data = self.data_context.get() or []
        now = datetime.now()

        for real_idx, rec in enumerate(data):
            unloads_all = rec.get("Выгрузка", [])
            processed = rec.get("processed", [])

            if not unloads_all or not isinstance(unloads_all, list):
                continue

            # ✅ как в TableManager: берём только точки (без Комментарий / "Выгрузка другое")
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
                        brush = QBrush(QColor("#FFD6D6"))
                        item = self.table.item(visual_row, 5)
                        if item:
                            item.setBackground(brush)
                        break
                except Exception:
                    continue
