from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel
from PyQt6.QtWidgets import QPushButton, QHBoxLayout
from PyQt6.QtGui import QPixmap, QDesktopServices
from PyQt6.QtCore import Qt, QUrl

from Navigation_Bot.gui.dialogs.add_note_dialog import AddNoteDialog
from Navigation_Bot.core.domain.entities.note import Note
from datetime import datetime


# TODO: Определить общую папку куда будет складываться все файлы со всех User
class NavigationHistoryDialog(QDialog):
    def __init__(self,
                 task_index: int,
                 nav_rows: list[dict],
                 vehicle_monitoring_id=None,
                 vehicle_plate: str = "",
                 vehicle_nav_rows: list[dict] | None = None,
                 route_rows: list[dict] | None = None,
                 note_rows: list[dict] | None = None,
                 note_history_service=None,
                 parent=None, ):

        super().__init__(parent)
        self.task_index = task_index
        self.vehicle_monitoring_id = vehicle_monitoring_id
        self.vehicle_plate = vehicle_plate
        self.note_rows = note_rows or []
        self.note_history_service = note_history_service
        self.race_nav_rows = nav_rows or []
        self.vehicle_nav_rows = vehicle_nav_rows or []
        self.nav_rows = self.race_nav_rows
        self.route_rows = route_rows or []
        self.history_mode = "race"
        self.rows = self._build_rows()
        self.setWindowTitle("История навигации")
        self.resize(1000, 500)

        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "Дата",
            "ТС",
            "Гео",
            "Координаты",
            "Скорость",
            "Осталось",
            "ETA",
            "Запас",
            "Куда",
            "GPS",
            "Старая",
        ])
        top = QHBoxLayout()

        self.btn_race_history = QPushButton("История рейса")
        self.btn_vehicle_history = QPushButton("История ТС")
        self.btn_race_history.setCheckable(True)
        self.btn_vehicle_history.setCheckable(True)
        self.btn_race_history.setChecked(True)
        self.btn_vehicle_history.setEnabled(bool(self.vehicle_monitoring_id))
        self.btn_race_history.clicked.connect(lambda: self._set_history_mode("race"))
        self.btn_vehicle_history.clicked.connect(lambda: self._set_history_mode("vehicle"))
        top.addWidget(self.btn_race_history)
        top.addWidget(self.btn_vehicle_history)
        self.btn_add_note = QPushButton("Добавить заметку")
        top.addStretch()
        top.addWidget(self.btn_add_note)
        self.btn_add_note.clicked.connect(self._on_add_note_clicked)
        layout.addLayout(top)

        layout.addWidget(self.table)
        self._fill()

    def _on_add_note_clicked(self):

        dlg = AddNoteDialog(parent=self)
        if not dlg.exec():
            return

        payload = dlg.get_payload()
        text = payload.get("text", "")
        media_paths = payload.get("media_paths", [])

        if not text and not media_paths:
            return

        note = Note(task_index=self.task_index,
                    text=text,
                    media_paths=media_paths,
                    media_type=self._detect_media_type(media_paths),
                    author="user", )

        if self.note_history_service:
            self.note_history_service.append(note)

        self.note_rows.append({"task_index": note.task_index,
                               "created_at": note.created_at,
                               "text": note.text,
                               "media_paths": note.media_paths,
                               "media_type": note.media_type,
                               "author": note.author, })

        self.history_mode = "race"
        self._sync_mode_buttons()
        self.rows = self._build_rows()
        self._fill()

    def _detect_media_type(self, paths: list[str]) -> str:
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

    def _open_media(self, path: str):
        path_obj = Path(path)
        if not path_obj.exists():
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path_obj)))

    def _build_media_preview(self, path: str):
        path_obj = Path(path)
        if not path_obj.exists():
            return None

        image_ext = {".png", ".jpg", ".jpeg", ".webp"}
        video_ext = {".mp4", ".mov", ".avi"}

        suffix = path_obj.suffix.lower()

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.mousePressEvent = lambda event, p=str(path_obj): self._open_media(p)
        if suffix in image_ext:
            pix = QPixmap(str(path_obj))
            if pix.isNull():
                return None

            pix = pix.scaled(110,
                             90,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation, )
            label.setPixmap(pix)
            return label

        if suffix in video_ext:
            label.setText(f"🎬 Видео\n{path_obj.name}")
            return label

        label.setText(f"📎 Файл\n{path_obj.name}")
        return label

    def _fill(self):
        self.btn_add_note.setEnabled(self.history_mode == "race")
        self.table.setRowCount(len(self.rows))

        for row_idx, item in enumerate(self.rows):
            if item.get("kind") == "note":
                values = [
                    item.get("time", ""),
                    "заметка",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]

                for col_idx, value in enumerate(values):
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

                media_paths = item.get("media_paths", []) or []
                text = item.get("geo", "")

                # Колонка 2 = "Гео" — туда кладём текст заметки
                self.table.setItem(row_idx, 2, QTableWidgetItem(text))

                # Колонка 3 = "Координаты" — туда кладём превью фото/видео
                if media_paths:
                    preview = self._build_media_preview(media_paths[0])
                    if preview:
                        self.table.setCellWidget(row_idx, 3, preview)
                        self.table.setRowHeight(row_idx, 120)

                continue
            else:
                values = [item.get("time", ""),
                          item.get("vehicle", ""),
                          item.get("geo", ""),
                          item.get("coords", ""),
                          str(item.get("speed", "") or ""),
                          f"Осталось {item.get('distance', '')}",
                          f"ETA {item.get('eta', '')}",
                          f"Запас {item.get('buffer', '')}",
                          f"Едет к {item.get('target', '')}",
                          item.get("gps", ""),
                          "Да" if item.get("stale") else "Нет",
                          ]

            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        self.table.resizeColumnsToContents()

    def _set_history_mode(self, mode: str):
        self.history_mode = mode if mode in {"race", "vehicle"} else "race"
        self._sync_mode_buttons()
        self.rows = self._build_rows()
        self._fill()

    def _sync_mode_buttons(self):
        self.btn_race_history.setChecked(self.history_mode == "race")
        self.btn_vehicle_history.setChecked(self.history_mode == "vehicle")

    def _build_rows(self):
        if self.history_mode == "vehicle":
            self.nav_rows = self.vehicle_nav_rows
            return self._merge_history(self.vehicle_nav_rows, [], [])

        self.nav_rows = self.race_nav_rows
        return self._merge_history(self.race_nav_rows, self.route_rows, self.note_rows)

    def _merge_history(self, nav_rows, route_rows, note_rows=None):
        note_rows = note_rows or []
        result = []

        for i, nav in enumerate(nav_rows):
            route = route_rows[i] if i < len(route_rows) else None

            distance = ""
            eta = ""
            buffer_text = ""
            target = ""

            if route:
                distance = f"{route.get('distance_km', 0)} км"
                eta = route.get("arrival_time", "")
                buffer_text = self._format_buffer(route.get("buffer_minutes", 0))
                target = f"#{route.get('target_sequence', '')}"

            result.append({"kind": "navigation",
                           "time": nav.get("collected_at", ""),
                           "vehicle": nav.get("vehicle_plate", ""),
                           "geo": nav.get("geo_text", ""),
                           "coords": nav.get("coordinates", ""),
                           "speed": nav.get("speed_kmh", ""),
                           "distance": distance,
                           "eta": eta,
                           "buffer": buffer_text,
                           "target": target,
                           "gps": nav.get("gps_fix_text", ""),
                           "stale": nav.get("is_navigation_stale", False),
                           })

        for note in note_rows:
            result.append({"kind": "note",
                           "time": note.get("created_at", ""),
                           "vehicle": "",
                           "geo": note.get("text", ""),
                           "coords": "",
                           "speed": "",
                           "distance": "",
                           "eta": "",
                           "buffer": "",
                           "target": "",
                           "gps": "",
                           "stale": False,
                           "media_paths": note.get("media_paths", []),
                           })

        def _parse_time(val):
            if not val:
                return datetime.min

            if isinstance(val, datetime):
                return val

            s = str(val)
            try:
                return datetime.fromisoformat(s)
            except Exception:
                pass

            fmts = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
                    "%d.%m %H:%M:%S", "%d.%m %H:%M", "%d.%m")
            for fmt in fmts:
                try:
                    dt = datetime.strptime(s, fmt)
                    if "%Y" not in fmt:
                        dt = dt.replace(year=datetime.now().year)
                    return dt
                except Exception:
                    continue

            return datetime.min

        result.sort(key=lambda x: _parse_time(x.get("time", "")), reverse=True)

        return result

    def _format_buffer(self, minutes: int) -> str:
        if minutes is None:
            return ""

        hours = minutes // 60
        mins = minutes % 60

        if hours and mins:
            return f"{hours}ч {mins}м"
        if hours:
            return f"{hours}ч"
        return f"{mins}м"

    def _format_route_estimate_text(self, estimate: dict) -> str:
        buffer_text = self._format_buffer(estimate.get("buffer_minutes", 0))

        return (f"{estimate.get('calculated_at', '')} | "
                f"Едет к выгрузке #{estimate.get('target_sequence', '')} | "
                f"Осталось {estimate.get('distance_km', 0)} км | "
                f"ETA {estimate.get('arrival_time', '')} | "
                f"Запас {buffer_text}"
                )
