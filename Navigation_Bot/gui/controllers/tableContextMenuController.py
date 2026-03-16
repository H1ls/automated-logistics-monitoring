from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from Navigation_Bot.bots.dataCleaner import DataCleaner


class TableContextMenuController:
    def __init__(self, gui):
        self.gui = gui
        self.table = gui.table

    def install(self):
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_menu)

    def _on_menu(self, pos):
        visual_row = self.table.rowAt(pos.y())
        real_idx = self._visual_to_real(visual_row)
        if real_idx is None:
            return

        menu = QMenu(self.table)
        act_refresh = menu.addAction("🔄 Перезаписать из Google (по index)")
        act_delete = menu.addAction("🗑 Удалить строку")
        menu.addSeparator()
        act_stub2 = menu.addAction("2) заглушка")
        act_stub3 = menu.addAction("3) заглушка")
        act_stub4 = menu.addAction("4) заглушка")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen == act_delete:
            self._delete_row(real_idx)
        elif chosen == act_refresh:
            self._refresh_row(real_idx)
            return


        else:
            self.gui.log("ℹ️ Пункт пока заглушка")

    def _visual_to_real(self, visual_row: int) -> int | None:
        if visual_row < 0:
            return None
        # последняя строка "➕"
        if visual_row >= self.table.rowCount() - 1:
            return None
        try:
            return self.gui.table_manager.view_order[visual_row]
        except Exception:
            return None

    def _delete_row(self, real_idx: int):
        data = self.gui.data_context.get() or []
        if not (0 <= real_idx < len(data)):
            return
        item = data.pop(real_idx)
        self.gui.data_context.save()
        self.gui.log(f"🗑 Удалено: ТС={item.get('ТС')} index={item.get('index')}")
        self.gui.reload_and_show()

    def _refresh_row(self, real_idx: int):
        try:
            data = self.gui.data_context.get() or []
            if not (0 <= real_idx < len(data)):
                return

            index_key = data[real_idx].get("index")
            if not index_key:
                self.gui.log("⚠️ В строке нет 'index'")
                return

            if not getattr(self.gui.gsheet, "sheet", None):
                self.gui.log("⚠️ Google Sheets не инициализирован")
                return

            rng = f"D{index_key}:H{index_key}"
            rows = self.gui.gsheet.sheet.get(rng)
            if not rows:
                self.gui.log(f"❌ Пусто в Google для {index_key}")
                return

            dh = rows[0]
            while len(dh) < 5:
                dh.append("")

            # 1 обновляем JSON
            self.gui.gsheet.refresh_name({index_key: dh}, update_existing=True)

            # 2 чистим ТОЛЬКО эту строку
            DataCleaner(data_context=self.gui.data_context, log_func=self.gui.log).start_clean(only_indexes={index_key})

            # 3 ОДИН раз обновляем UI
            self.gui.reload_and_show()

            self.gui.log(f"✅ Точечное обновление выполнено: index={index_key}")

        except Exception as e:
            self.gui.log(f"❌ Ошибка точечного обновления: {e}")
