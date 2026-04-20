from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu


class TableContextMenuController:
    def __init__(self, gui, tasks_service=None, google_sync_service=None):
        self.gui = gui
        self.table = gui.table
        self.tasks = tasks_service
        self.google_sync = google_sync_service
        # self.google_sync = getattr(gui, "google_sync_service", None)

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
        try:
            return self.gui.table_manager.view_order[visual_row]
        except Exception:
            return None

    def _delete_row(self, real_idx: int):
        if not self.tasks:
            self.gui.log("⚠️ TasksService не подключён")
            return

        ok, item, err = self.tasks.delete_row(real_idx)
        if not ok:
            self.gui.log(f"❌ Не удалось удалить строку: {err}")
            return

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

            if not self.google_sync:
                self.gui.log("⚠️ GoogleSyncService не подключён")
                return

            ok, updated_task, err = self.google_sync.refresh_row_by_index(index_key)
            if not ok:
                self.gui.log(f"❌ Ошибка точечного обновления: {err}")
                return

            self.gui.reload_and_show()
            self.gui.log(f"✅ Точечное обновление выполнено: строки ={index_key} в Goggle.")

        except Exception as e:
            self.gui.log(f"❌ Ошибка точечного обновления: {e}")
