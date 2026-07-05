from __future__ import annotations

from collections.abc import Iterable

from Navigation_Bot.core.infrastructure.persistence.dataset_archive import DatasetArchive
from Navigation_Bot.gui.widgets.address_point_editor import AddressPointEditor


class AddressArchiveService:
    def __init__(self, log_func=print):
        self.log = log_func

    def archive_sample(self, *, editors: Iterable[AddressPointEditor], comment: str, raw_input: str) -> None:
        try:
            output = [item for editor in editors
                      if (item := editor.archive_dict()) is not None]
            comment = comment.strip()
            if comment:
                if output:
                    output[-1]["Комментарий"] = comment
                else:
                    output.append({"Адрес": "", "Дата": "", "Время": "", "Комментарий": comment})

            DatasetArchive(log_func=self.log).append({"input": raw_input, "output": output})
            self.log(f"📦 В архив добавлено: {raw_input[:60]}...")
        except Exception as exc:
            self.log(f"❌ Ошибка в _archive_sample: {exc}")
