from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu

from Navigation_Bot.gui.dialogs.add_note_dialog import AddNoteDialog
from Navigation_Bot.core.domain.entities.note import Note
from Navigation_Bot.core.task_identity import google_sheet_row, row_identity_for_gui, trip_number


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

        rec = self._get_row(real_idx)
        if rec is None:
            return

        menu = QMenu(self.table)
        act_refresh = menu.addAction("🔄 Перезаписать из Google")  # по google_sheet_row
        act_complete = menu.addAction("Завершить рейс")
        menu.addSeparator()

        act_add_note = menu.addAction("📝 Добавить заметку")
        duration_actions = {}
        if rec.get("highlight_until"):
            act_stub4 = menu.addAction("⚪ Убрать подсветку")
        else:
            act_stub4 = None
            highlight_menu = menu.addMenu("🟢 Подсветить строку")
            for hours in (1, 2, 3, 6, 12, 24):
                label = f"{hours}ч"
                duration_actions[highlight_menu.addAction(label)] = hours

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen == act_complete:
            self._complete_row(real_idx)
        elif chosen == act_refresh:
            self._refresh_row(real_idx)
            return
        elif chosen == act_add_note:
            self._add_note(real_idx)
            return
        elif chosen in duration_actions:
            self._set_highlight(real_idx, duration_actions[chosen])
            return
        elif chosen == act_stub4:
            self._toggle_highlight(real_idx)
            return

    def _get_row(self, real_idx: int) -> dict | None:
        if self.tasks:
            return self.tasks.get_row(real_idx)

        data = self.gui.task_repository.get() or []
        if not (0 <= real_idx < len(data)):
            return None
        row = data[real_idx]
        return row if isinstance(row, dict) else None

    def _add_note(self, real_idx: int):
        try:
            row = self._get_row(real_idx)
            if row is None:
                self.gui.log("⚠️ Строка не найдена")
                return

            task_trip_number = trip_number(row)
            if not task_trip_number:
                self.gui.log("⚠️ У строки нет trip_number")
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

            note = Note(trip_number=task_trip_number,
                        text=text,
                        media_paths=media_paths,
                        media_type=self._detect_media_type(media_paths),
                        author="user")

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
            row = self._get_row(real_idx)
            if row is None:
                return

            row_identity = row_identity_for_gui(row)
            if not row_identity:
                self.gui.log("⚠️ В строке нет google_sheet_row/trip_number")
                return

            highlighter = getattr(self.gui, "row_highlighter", None)
            if not highlighter:
                self.gui.log("⚠️ RowHighlighter не найден")
                return

            enabled = highlighter.toggle_highlight(row_identity)

            if enabled:
                self.gui.log(f"🟢 Подсветка включена: строки = {real_idx + 1},и ТС {row.get('ТС')}")
            else:
                self.gui.log(f"⚪ Подсветка снята: строки = {real_idx + 1}, и ТС {row.get('ТС')}")

        except Exception as e:
            self.gui.log(f"❌ Ошибка toggle_highlight: {e}")

    def _set_highlight(self, real_idx: int, hours: int):
        try:
            row = self._get_row(real_idx)
            if row is None:
                return

            row_identity = row_identity_for_gui(row)
            if not row_identity:
                self.gui.log("⚠️ В строке нет google_sheet_row/trip_number")
                return

            highlighter = getattr(self.gui, "row_highlighter", None)
            if not highlighter:
                self.gui.log("⚠️ RowHighlighter не найден")
                return

            highlighter.set_highlight_for(row_identity, hours=hours)
            # self.gui.log(f"🟢 Подсветка включена на {hours}ч: строки = {real_idx + 1}, и ТС {row.get('ТС')}")

        except Exception as e:
            self.gui.log(f"❌ Ошибка set_highlight: {e}")

    def _visual_to_real(self, visual_row: int) -> int | None:
        if visual_row < 0:
            return None
        try:
            return self.gui.table_manager.view_order[visual_row]
        except Exception:
            return None

    def _complete_row(self, real_idx: int):
        if not self.tasks:
            self.gui.log("⚠️ TasksService не подключён")
            return

        ok, item, err = self.tasks.complete_row(real_idx, source="user")
        if not ok:
            self.gui.log(f"❌ Не удалось завершить рейс: {err}")
            return

        self.gui.log(f"✅ Рейс завершён: ТС = {item.get('ТС')},"
                     f"google_sheet_row = {google_sheet_row(item)},"
                     f"trip_number = {trip_number(item)}")
        self.gui.reload_and_show()

    def _refresh_row(self, real_idx: int):
        try:
            row = self._get_row(real_idx)
            if row is None:
                return

            row_google_sheet_row = google_sheet_row(row)
            if not row_google_sheet_row:
                self.gui.log("⚠️ В строке нет google_sheet_row")
                return

            if not self.google_sync:
                self.gui.log("⚠️ GoogleSyncService не подключён")
                return

            ok, updated_task, err = self.google_sync.refresh_row_by_google_sheet_row(row_google_sheet_row)
            if not ok:
                self.gui.log(f"❌ Ошибка точечного обновления: {err}")
                return

            self.gui.reload_and_show()
            self.gui.log(f"✅ Точечное обновление выполнено: строки = {row_google_sheet_row} в Google.")

        except Exception as e:
            self.gui.log(f"❌ Ошибка точечного обновления: {e}")
