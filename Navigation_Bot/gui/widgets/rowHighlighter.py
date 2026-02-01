from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor
from datetime import datetime, timedelta, timezone


class RowHighlighter:
    def __init__(self, table, data_context, log, hours_default=2):
        self.table = table
        self.data_context = data_context
        self.log = log
        self.hours_default = hours_default
        self.until_map = {}  # row_idx -> datetime(UTC)

    @staticmethod
    def _to_iso_utc(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _from_iso_utc(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    def highlight_for(self, row_idx: int, hours: int | None = None):
        data = self.data_context.get() or []
        if not (0 <= row_idx < len(data)):
            self.log(f"⚠️ highlight_for: нет такой строки {row_idx}")
            return

        hours = hours or self.hours_default
        until_dt = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=-5)
        until_iso = self._to_iso_utc(until_dt)

        self._paint_row(row_idx, enabled=True)
        self.until_map[row_idx] = until_dt

        rec = data[row_idx]
        rec["highlight_until"] = until_iso
        self.data_context.save()
        self.log(f"💾 highlight_until записан для row {row_idx}: {until_iso}")

        QTimer.singleShot(hours * 60 * 60 * 1000, lambda: self._clear_if_expired(row_idx))

    def reapply_from_json(self):
        """Вызывай после reload_and_show() - позиция = индекс в списке."""
        data = self.data_context.get() or []
        now = datetime.now(timezone.utc)
        changed = False

        for i, rec in enumerate(data):
            iso = rec.get("highlight_until")
            if not iso:
                continue
            try:
                until = self._from_iso_utc(iso)
            except Exception:
                rec.pop("highlight_until", None)
                changed = True
                continue

            if now < until:
                if 0 <= i < self.table.rowCount():
                    self._paint_row(i, enabled=True)
                    self.until_map[i] = until
            else:
                rec.pop("highlight_until", None)
                changed = True

        if changed:
            self.data_context.save()

        # после восстановления выделений - подсветка просроченных выгрузок
        self.highlight_expired_unloads()

    def _clear_if_expired(self, row_idx: int):
        data = self.data_context.get() or []
        until = self.until_map.get(row_idx)
        now = datetime.now(timezone.utc)

        if until and now >= until:
            self.until_map.pop(row_idx, None)
            if 0 <= row_idx < self.table.rowCount():
                self._paint_row(row_idx, enabled=False)
            if 0 <= row_idx < len(data):
                rec = data[row_idx]
                if rec.pop("highlight_until", None) is not None:
                    self.data_context.save()
                    self.log(f"🧽 highlight_until снят для row {row_idx}")

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
        from datetime import datetime
        from PyQt6.QtGui import QColor, QBrush

        data = self.data_context.get() or []
        now = datetime.now()

        for row_idx, rec in enumerate(data):
            unloads = rec.get("Выгрузка", [])
            processed = rec.get("processed", [])
            if not unloads or not isinstance(unloads, list):
                continue

            # находим первую непройденную точку (processed=False)
            for i, unload in enumerate(unloads):
                is_done = processed[i] if i < len(processed) else False
                if is_done:
                    continue

                date_key = f"Дата {i + 1}"
                time_key = f"Время {i + 1}"
                date_str = unload.get(date_key, "")
                time_str = unload.get(time_key, "")

                if not date_str or not time_str:
                    continue

                try:
                    if time_str.count(":") == 1:
                        time_str += ":00"
                    dt_unload = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")

                    if dt_unload < now:
                        # подсветка светло-красным
                        brush = QBrush(QColor("#FFD6D6"))
                        item = self.table.item(row_idx, 5)
                        if item:
                            item.setBackground(brush)
                        break  # только первую просроченную отмечаем
                except Exception:
                    continue
