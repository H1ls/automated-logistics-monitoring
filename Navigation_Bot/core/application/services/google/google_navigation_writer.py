from __future__ import annotations

from datetime import datetime
from typing import Any

from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry


class GoogleNavigationWriter:
    def __init__(self, gsheet, log=None):
        self.gsheet = gsheet
        self.log = log
        self._sites_db = SitesDbRegistry(log_func=log)

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)
        elif hasattr(self.gsheet, "_log"):
            self.gsheet._log(msg)

    @property
    def sheet(self):
        return getattr(self.gsheet, "sheet", None)

    def append_to_cell(self, data, column=12):
        self._sites_db.reload()
        if isinstance(data, list):
            for item in data:
                self._append_entry(item, column)
        elif isinstance(data, dict):
            self._append_entry(data, column)

    def _append_entry(self, item: dict[str, Any], column: int) -> None:
        try:
            if not self.sheet:
                self._log("⚠️ Лист Google Sheets не инициализирован")
                return

            row_index = item.get("index")
            if not row_index:
                self._log("⚠️ Пропуск записи: нет индекса строки")
                return

            current_time = datetime.now().strftime("%d-%m %H:%M")

            geo = item.get("гео") or ""
            geo_zona = str(item.get("geo_zona") or "").strip()
            coor = item.get("коор") or ""
            speed = item.get("скорость")

            zone_label = self._sites_db.match_geo_zona_to_zone_label(geo_zona, item)

            if zone_label:
                new_text = f"{current_time} {zone_label}"
            elif geo == "нет навигации":
                new_text = f"{current_time} нет навигации"
            elif not geo and not coor:
                self._log(f"⚠️ Пропуск строки {row_index}: нет гео/координат")
                return
            else:
                status = "стоит" if isinstance(speed, (int, float)) and speed < 5 else "едет"
                new_text = f"{current_time} {status} {geo}{' ' + coor if coor else ''}"

            try:
                cell_value = self.sheet.cell(row_index, column).value
            except Exception as e:
                self._log(f"⚠️ Не удалось прочитать ячейку {row_index}, кол. {column}: {e}")
                cell_value = ""

            updated_value = f"{cell_value}\n{new_text}" if cell_value else new_text
            self.sheet.update_cell(row_index, column, updated_value)
            self._log(f"🌎 Обновлена строка {row_index}, колонка {column}")

        except Exception as e:
            self._log(f"❌ Ошибка при записи строки {item.get('ТС')}: {e}")

    def upload_new_row(self, entry: dict) -> int:
        try:
            if not self.sheet:
                self._log("⚠️ Лист Google Sheets не инициализирован")
                raise RuntimeError("google_sheet_not_initialized")

            row_index = entry.get("google_sheet_row") or self._next_empty_task_row()
            ts_with_phone = f"{entry.get('ТС', '')} {entry.get('Телефон', '')}".strip()

            load_str = "; ".join(
                f"{blk.get(f'Время {i + 1}', '')} {blk.get(f'Погрузка {i + 1}', '')}".strip()
                for i, blk in enumerate(entry.get("Погрузка", []))
            )

            unload_str = "; ".join(
                f"{blk.get(f'Время {i + 1}', '')} {blk.get(f'Выгрузка {i + 1}', '')}".strip()
                for i, blk in enumerate(entry.get("Выгрузка", []))
            )

            row_data = [
                ts_with_phone,
                entry.get("ФИО", ""),
                entry.get("КА", ""),
                load_str,
                unload_str,
            ]

            self.sheet.update(f"D{row_index}:H{row_index}", [row_data])
            self._log(f"📤 Новая запись отправлена в Google Sheets (row={row_index})")
            return int(row_index)

        except Exception as e:
            self._log(f"❌ Ошибка выгрузки новой строки: {e}")
            raise

    def _next_empty_task_row(self) -> int:
        values = self.sheet.get("D3:H")
        for offset, row in enumerate(values or []):
            if not any(str(cell or "").strip() for cell in row):
                return 3 + offset
        return 3 + len(values or [])

    def write_all(self, items: list):
        if not items:
            self._log("⚠️ Нет данных для записи в Google Sheets")
            return

        try:
            self.append_to_cell(items)
        except Exception as e:
            self._log(f"❌ Ошибка при записи в Google Sheets: {e}")
