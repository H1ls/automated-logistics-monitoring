from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class TasksService:
    """
    Тонкий слой над DataContext для операций CRUD.
    """

    data_context: Any
    gsheet: Any | None = None
    log: Callable[[str], None] | None = None

    def delete_row(self, real_idx: int) -> dict | None:
        data = self.data_context.get() or []
        if not (0 <= real_idx < len(data)):
            return None
        item = data.pop(real_idx)
        self.data_context.save()
        return item

    def update_editable_field(self, real_idx: int, header: str, value: str) -> tuple[bool, str | None]:
        """
        Обновить одно поле в строке.
        Возвращает (ok, error_message).
        """
        data = self.data_context.get() or []
        if not (0 <= real_idx < len(data)):
            return False, "row_out_of_range"

        if header == "id":
            if not str(value).strip():
                return False, "empty_id"
            if not str(value).strip().isdigit():
                return False, "invalid_id"
            value = int(str(value).strip())
        else:
            value = str(value)

        old_value = (data[real_idx] or {}).get(header)
        if old_value == value:
            return True, None

        data[real_idx][header] = value
        self.data_context.save()
        return True, None

    def add_entry_from_new_row(self,ts_phone: str,ka: str,fio: str,new_entry_buffer: dict,
) -> tuple[bool, dict | None, str | None]:
        """
        Создать и сохранить новую запись на основе данных из "ключевой строки" таблицы.
        Возвращает (ok, new_entry, error_message).
        """
        ts_phone = (ts_phone or "").strip()
        ka = (ka or "").strip()
        fio = (fio or "").strip()

        if not ts_phone or "Погрузка" not in (new_entry_buffer or {}) or "Выгрузка" not in (new_entry_buffer or {}):
            return False, None, "missing_required_fields"

        parts = ts_phone.split()
        ts = " ".join(parts[:-1]) if len(parts) > 1 else ts_phone
        phone = parts[-1] if len(parts) > 1 else ""

        new_entry = {"ТС": ts,
                     "Телефон": phone,
                     "ФИО": fio,
                     "КА": ka,
                     "Погрузка": (new_entry_buffer or {}).get("Погрузка", []),
                     "Выгрузка": (new_entry_buffer or {}).get("Выгрузка", []),}

        if "Время отправки" in (new_entry_buffer or {}):
            new_entry["Время отправки"] = new_entry_buffer["Время отправки"]
        if "Транзит" in (new_entry_buffer or {}):
            new_entry["Транзит"] = new_entry_buffer["Транзит"]

        data = self.data_context.get() or []
        last_index = max([x.get("index", 0) for x in data if isinstance(x, dict)], default=0)
        index = last_index + 1

        # при наличии gsheet — выбираем свободную строку там
        if self.gsheet and hasattr(self.gsheet, "is_row_empty"):
            try:
                while not self.gsheet.is_row_empty(index):
                    index += 1
            except Exception:
                # если проверка гугла упала — всё равно проставим index последовательно
                pass

        new_entry["index"] = index

        data.append(new_entry)
        self.data_context.save()

        # отправляем в Google Sheets (если доступно)
        if self.gsheet and hasattr(self.gsheet, "upload_new_row"):
            try:
                self.gsheet.upload_new_row(new_entry)
                new_entry["uploaded"] = True
                self.data_context.save()
            except Exception as e:
                if self.log:
                    self.log(f"⚠️ Не удалось загрузить новую строку в Google: {e}")

        return True, new_entry, None
