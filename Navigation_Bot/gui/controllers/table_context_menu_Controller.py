from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from Navigation_Bot.gui.dialogs.add_note_dialog import AddNoteDialog
from Navigation_Bot.core.domain.entities.note import Note


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
        # TODO: Изменить взаимодействия с task_repository
        data = self.gui.task_repository.get() or []
        if not (0 <= real_idx < len(data)):
            return

        rec = data[real_idx]
        menu = QMenu(self.table)
        act_refresh = menu.addAction("🔄 Перезаписать из Google (по index)")
        act_delete = menu.addAction("🗑 Удалить строку")
        menu.addSeparator()

        # TODO: Заполнить act_stub2
        act_stub2 = menu.addAction("2) заглушка")
        act_add_note = menu.addAction("📝 Добавить заметку")
        if rec.get("highlight_until"):
            act_stub4 = menu.addAction("⚪ Убрать подсветку")
        else:
            act_stub4 = menu.addAction("🟢 Подсветить строку")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen == act_delete:
            self._delete_row(real_idx)
        elif chosen == act_refresh:
            self._refresh_row(real_idx)
            return
        elif chosen == act_add_note:
            self._add_note(real_idx)
            return
        elif chosen == act_stub4:
            self._toggle_highlight(real_idx)
            return

        else:
            self.gui.log("ℹ️ Пункт пока заглушка")

    def _add_note(self, real_idx: int):
        try:
            data = self.gui.task_repository.get() or []
            if not (0 <= real_idx < len(data)):
                self.gui.log("⚠️ Строка не найдена")
                return

            row = data[real_idx] or {}
            task_index = row.get("index")
            if not task_index:
                self.gui.log("⚠️ У строки нет index")
                return

            note_service = getattr(self.gui, "note_history_service", None)
            if not note_service:
                self.gui.log("⚠️ note_history_service не подключён")
                return

            dlg = AddNoteDialog(parent=self.table)
            if not dlg.exec():
                return

            payload = dlg.get_payload()
            text = payload.get("text", "")
            media_paths = payload.get("media_paths", [])

            if not text and not media_paths:
                return

            note = Note(task_index=task_index,
                        text=text,
                        media_paths=media_paths,
                        media_type=self._detect_media_type(media_paths),
                        author="user",
                        )

            note_service.append(note)

            ts = row.get("ТС", "")
            self.gui.log(f"📝 Заметка добавлена: ТС={ts}")

        except Exception as e:
            self.gui.log(f"❌ Ошибка добавления заметки: {e}")

    def _detect_media_type(self, paths: list[str]) -> str:
        from pathlib import Path

        if not paths:
            return ""

        image_ext = {".png", ".jpg", ".jpeg", ".webp"}
        video_ext = {".mp4", ".mov", ".avi"}

        has_image = False
        has_video = False

        for p in paths:
            suffix = Path(p).suffix.lower()
            if suffix in image_ext:
                has_image = True
            elif suffix in video_ext:
                has_video = True

        if has_image and has_video:
            return "mixed"
        if has_image:
            return "photo"
        if has_video:
            return "video"
        return "file"

    def _toggle_highlight(self, real_idx: int):
        try:
            data = self.gui.task_repository.get() or []
            if not (0 <= real_idx < len(data)):
                return

            index_key = data[real_idx].get("index")
            if not index_key:
                self.gui.log("⚠️ В строке нет 'index'")
                return

            highlighter = getattr(self.gui, "row_highlighter", None)
            if not highlighter:
                self.gui.log("⚠️ RowHighlighter не найден")
                return

            enabled = highlighter.toggle_highlight(index_key)

            # TODO: Если highlighter есть какой то, то он не предлагает подстветить сразу
            if enabled:
                self.gui.log(f"🟢 Подсветка включена: строки = {real_idx + 1},и ТС {data[real_idx].get("ТС")}")
            else:
                self.gui.log(f"⚪ Подсветка снята: строки = {real_idx + 1}, и ТС {data[real_idx].get("ТС")}")

        except Exception as e:
            self.gui.log(f"❌ Ошибка toggle_highlight: {e}")

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
            data = self.gui.task_repository.get() or []
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
