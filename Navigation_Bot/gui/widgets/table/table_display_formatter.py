from __future__ import annotations

from PyQt6.QtGui import QFontMetrics
from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry


class TableDisplayFormatter:
    def __init__(self, log_func=None):
        self._sites_db = SitesDbRegistry(log_func=log_func)

    def reload_sites_db(self) -> None:
        self._sites_db.reload()

    def _format_address_line(self, address: str) -> str:
        """
        есть совпадение с aliases — только адрес; нет — «❓» перед адресом.
        """

        address = (address or "").strip()
        if not address:
            return ""
        if self._sites_db.is_address_known(address):
            return address
        return f"❓ {address}"

    @staticmethod
    def _column_separator_line(table, col: int | None) -> str:
        """Разделитель на всю ширину ячейки колонки (по метрикам шрифта таблицы)."""

        if table is None or col is None:
            return "____________________"

        width_px = table.columnWidth(col)
        usable_px = max(24, width_px - 12)  # небольшой запас под отступы ячейки

        fm = QFontMetrics(table.font())
        unit = fm.horizontalAdvance("_") or 4
        count = max(8, usable_px // unit)
        return "_" * count

    @staticmethod
    def split_points_and_comment(blocks: list[dict], prefix: str):
        points = []
        comment = ""

        for d in blocks or []:
            if not isinstance(d, dict):
                continue

            if "Комментарий" in d:
                comment = str(d.get("Комментарий", "")).strip()
            elif f"{prefix} другое" in d:
                comment = str(d.get(f"{prefix} другое", "")).strip()
            elif any(k.startswith(f"{prefix} ") for k in d.keys()):
                points.append(d)

        return points, comment

    def field_with_datetime(self,
                            row: dict,
                            key: str,
                            *,
                            point_suffixes: list[str] | None = None,
                            separator_table=None,
                            separator_col: int | None = None,
                            ) -> str:

        blocks = row.get(key)

        if not isinstance(blocks, list):
            return ""

        points = []
        comment = ""

        for d in blocks:
            if not isinstance(d, dict):
                continue
            if "Комментарий" in d:
                comment = str(d.get("Комментарий", "")).strip()
                continue
            if f"{key} другое" in d:
                comment = str(d.get(f"{key} другое", "")).strip()
                continue
            points.append(d)

        lines = []
        for i, block in enumerate(points, 1):
            date = block.get(f"Дата {i}", "")
            time = block.get(f"Время {i}", "")
            address = block.get(f"{key} {i}", "")
            dt = f"{date} {time}".strip()

            if dt and dt != "Не указано Не указано":
                lines.append(dt)
            if address:
                address_line = self._format_address_line(address)
                if point_suffixes and i - 1 < len(point_suffixes):
                    suffix = point_suffixes[i - 1]
                    if suffix:
                        address_line = f"{address_line}  {suffix}"
                lines.append(address_line)
            if i < len(points):
                lines.append(self._column_separator_line(separator_table, separator_col))

        if comment:
            if lines:
                lines.append("")
            lines.append("Комментарий:")
            lines.append(comment)

        return "\n".join(lines)

    def points_text(self, points: list[dict], *, point_suffixes: list[str] | None = None, separator_table=None,
                    separator_col: int | None = None, ) -> str:

        if not isinstance(points, list):
            return ""

        lines = []
        for idx, point in enumerate(points, 1):
            if not isinstance(point, dict):
                continue

            date = str(point.get("date") or "").strip()
            time = str(point.get("time") or "").strip()
            address = str(point.get("address") or "").strip()
            comment = str(point.get("comment") or "").strip()
            dt = f"{date} {time}".strip()

            if dt:
                lines.append(dt)
            if address:
                address_line = self._format_address_line(address)
                if point_suffixes and idx - 1 < len(point_suffixes):
                    suffix = point_suffixes[idx - 1]
                    if suffix:
                        address_line = f"{address_line}  {suffix}"
                lines.append(address_line)
            if comment:
                lines.append("Комментарий:")
                lines.append(comment)
            if idx < len(points):
                lines.append(self._column_separator_line(separator_table, separator_col))

        return "\n".join(lines)

    def unload_points_text_with_status(self,row: dict,*,separator_table=None,separator_col: int | None = None) -> str:

        points = row.get("unloads")
        if not isinstance(points, list):
            return ""

        processed = row.get("processed_unloads")
        if not isinstance(processed, list):
            processed = []

        point_suffixes = None
        address_indexes = [
            idx for idx, point in enumerate(points)
            if isinstance(point, dict) and str(point.get("address") or "").strip()
        ]
        if len(address_indexes) > 1:
            point_suffixes = [""] * len(points)
            for processed_idx, point_idx in enumerate(address_indexes):
                point_suffixes[point_idx] = (
                    "☑️" if (processed_idx < len(processed) and processed[processed_idx]) else "⬜️"
                )

        return self.points_text(points,
                                point_suffixes=point_suffixes,
                                separator_table=separator_table,
                                separator_col=separator_col,
                                )

    def unload_text_with_status(self,row: dict,*,separator_table=None,separator_col: int | None = None) -> str:

        points, _ = self.split_points_and_comment(row.get("Выгрузка", []), "Выгрузка")
        processed = row.get("processed", []) or []

        point_suffixes = None
        if len(points) > 1:
            point_suffixes = [
                "☑️" if (idx < len(processed) and processed[idx]) else "⬜️"
                for idx in range(len(points))
            ]

        return self.field_with_datetime(row,
                                        "Выгрузка",
                                        point_suffixes=point_suffixes,
                                        separator_table=separator_table,
                                        separator_col=separator_col,
                                        )

    @staticmethod
    def route_buffer_text(route: dict) -> str:
        buffer = route.get("time_buffer", "—")

        if isinstance(buffer, str) and ":" in buffer:
            try:
                h, m = map(int, buffer.split(":"))
                return f"{h}ч {m}м"
            except Exception:
                return buffer

        return buffer
