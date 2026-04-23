from __future__ import annotations


class TableDisplayFormatter:
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

    @staticmethod
    def field_with_datetime(row: dict, key: str) -> str:
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
                lines.append(address)
            if i < len(points):
                lines.append("____________________")

        if comment:
            if lines:
                lines.append("")
            lines.append("Комментарий:")
            lines.append(comment)

        return "\n".join(lines)

    @classmethod
    def unload_text_with_status(cls, row: dict) -> str:
        unloads_all = row.get("Выгрузка", [])
        points, comment = cls.split_points_and_comment(unloads_all, "Выгрузка")
        processed = row.get("processed", [])

        if len(points) <= 1:
            temp_row = dict(row)
            temp_row["Выгрузка"] = points
            base_text = cls.field_with_datetime(temp_row, "Выгрузка")
            if comment:
                return base_text + ("\n\nКомментарий:\n" + comment) if base_text else "Комментарий:\n" + comment
            return base_text

        text_parts = []
        for i, unload in enumerate(points, start=1):
            prefix = f"Выгрузка {i}"
            address = unload.get(prefix, "")
            date = unload.get(f"Дата {i}", "")
            time = unload.get(f"Время {i}", "")
            checked = processed[i - 1] if i - 1 < len(processed) else False
            checkbox = "☑️" if checked else "⬜️"
            part = f"{date} {time}\n{address}  {checkbox}"
            text_parts.append(part.strip())

        if comment:
            text_parts.append("")
            text_parts.append("Комментарий:")
            text_parts.append(comment)

        return "\n\n".join(text_parts)

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