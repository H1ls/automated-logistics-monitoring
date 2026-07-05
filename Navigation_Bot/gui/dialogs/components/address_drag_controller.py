from __future__ import annotations

from PyQt6.QtCore import QEvent, QMimeData, QPoint, Qt
from PyQt6.QtGui import QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from Navigation_Bot.gui.widgets.address_point_editor import AddressPointEditor


class AddressPointDragController:
    MIME_TYPE = "application/x-address-point-editor"

    def __init__(self, dialog):
        self.dialog = dialog
        self._drag_editor: AddressPointEditor | None = None
        self._drag_start_pos = QPoint()
        self._drag_placeholder: QWidget | None = None
        self._drag_target_index: int | None = None

    def install_on_scroll_widget(self) -> None:
        self.dialog.scroll_widget.setAcceptDrops(True)
        self.dialog.scroll_widget.installEventFilter(self.dialog)

    def install_on_editor(self, editor: AddressPointEditor) -> None:
        editor.setAcceptDrops(True)
        editor.installEventFilter(self.dialog)
        editor.drag_handle.installEventFilter(self.dialog)

    def event_filter(self, watched, event) -> bool:
        if self._is_drag_handle(watched):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_editor = watched.property("address_editor")
                self._drag_start_pos = event.globalPosition().toPoint()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_editor is not None:
                distance = (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._start_entry_drag(self._drag_editor)
                    self._drag_editor = None
                    return True

        if watched in self.dialog.entries or watched is self.dialog.scroll_widget or watched is self._drag_placeholder:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasFormat(self.MIME_TYPE):
                    position = self._map_drop_position(watched, event.position().toPoint())
                    self._update_drag_placeholder(self._drop_visible_index(position.y()))
                    event.acceptProposedAction()
                    return True
            if event.type() == QEvent.Type.Drop:
                if event.mimeData().hasFormat(self.MIME_TYPE):
                    source_id = bytes(event.mimeData().data(self.MIME_TYPE)).decode("ascii")
                    source = self._entry_by_id(source_id)
                    if source is not None:
                        target_index = self._drag_target_index
                        if target_index is None:
                            position = self._map_drop_position(watched, event.position().toPoint())
                            target_index = self._entry_target_index_from_visible(self._drop_visible_index(position.y()))
                        self._move_entry(source, target_index)
                    event.acceptProposedAction()
                    return True

        return False

    @staticmethod
    def _is_drag_handle(widget) -> bool:
        return bool(widget.property("address_drag_handle"))

    def _start_entry_drag(self, editor: AddressPointEditor) -> None:
        drag = QDrag(editor)
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, str(id(editor)).encode("ascii"))
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap(editor))
        drag.setHotSpot(editor.drag_handle.mapTo(editor, editor.drag_handle.rect().center()))
        self._begin_drag_visuals(editor)
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._end_drag_visuals(editor)

    def _entry_by_id(self, editor_id: str) -> AddressPointEditor | None:
        for editor in self.dialog.entries:
            if str(id(editor)) == editor_id:
                return editor
        return None

    def _map_drop_position(self, watched, position: QPoint) -> QPoint:
        if watched is self.dialog.scroll_widget:
            return position
        return watched.mapTo(self.dialog.scroll_widget, position)

    def _drop_visible_index(self, y: int) -> int:
        visible_index = 0
        for editor in self.dialog.entries:
            if editor is self._drag_editor:
                continue
            if y < editor.geometry().center().y():
                return visible_index
            visible_index += 1
        return visible_index

    def _entry_target_index_from_visible(self, visible_index: int) -> int:
        visible_count = 0
        for index, editor in enumerate(self.dialog.entries):
            if editor is self._drag_editor:
                continue
            if visible_count == visible_index:
                return index
            visible_count += 1
        return len(self.dialog.entries)

    def _layout_index_for_visible_insert(self, visible_index: int) -> int:
        visible_count = 0
        for layout_index in range(self.dialog.scroll_layout.count()):
            item = self.dialog.scroll_layout.itemAt(layout_index)
            widget = item.widget() if item is not None else None
            if widget is None or widget is self._drag_placeholder or widget is self._drag_editor:
                continue
            if widget in self.dialog.entries:
                if visible_count == visible_index:
                    return layout_index
                visible_count += 1
        return max(self.dialog.scroll_layout.count() - 1, 0)

    def _begin_drag_visuals(self, editor: AddressPointEditor) -> None:
        self._drag_editor = editor
        self._drag_placeholder = QWidget(self.dialog.scroll_widget)
        self._drag_placeholder.setFixedHeight(max(editor.height(), editor.sizeHint().height()))
        self._drag_placeholder.setStyleSheet(
            "background: rgba(70, 130, 180, 25);"
            "border: 2px dashed #4682b4;"
            "border-radius: 4px;"
        )
        self._drag_placeholder.setAcceptDrops(True)
        self._drag_placeholder.installEventFilter(self.dialog)
        self._drag_target_index = self.dialog.entries.index(editor)
        editor.hide()
        self.dialog.scroll_layout.insertWidget(
            self._layout_index_for_visible_insert(self._drop_visible_index(editor.y())),
            self._drag_placeholder,
        )

    def _end_drag_visuals(self, editor: AddressPointEditor) -> None:
        if self._drag_placeholder is not None:
            self.dialog.scroll_layout.removeWidget(self._drag_placeholder)
            self._drag_placeholder.deleteLater()
        editor.show()
        self._drag_placeholder = None
        self._drag_target_index = None
        self._drag_editor = None
        self.dialog.schedule_resize_to_content()

    def _update_drag_placeholder(self, visible_index: int) -> None:
        if self._drag_placeholder is None:
            return
        self._drag_target_index = self._entry_target_index_from_visible(visible_index)
        self.dialog.scroll_layout.removeWidget(self._drag_placeholder)
        self.dialog.scroll_layout.insertWidget(
            self._layout_index_for_visible_insert(visible_index),
            self._drag_placeholder,
        )

    @staticmethod
    def _drag_pixmap(editor: AddressPointEditor) -> QPixmap:
        source = editor.grab()
        pixmap = QPixmap(source.size())
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setOpacity(0.88)
        painter.drawPixmap(0, 0, source)
        painter.end()
        return pixmap

    def _move_entry(self, editor: AddressPointEditor, target_index: int) -> None:
        self.move_entry(editor, target_index)

    def move_entry(self, editor: AddressPointEditor, target_index: int) -> None:
        if editor not in self.dialog.entries:
            return
        source_index = self.dialog.entries.index(editor)
        target_index = max(0, min(target_index, len(self.dialog.entries)))
        if target_index > source_index:
            target_index -= 1
        if source_index == target_index:
            return

        self.dialog.entries.pop(source_index)
        self.dialog.entries.insert(target_index, editor)
        self.dialog.scroll_layout.removeWidget(editor)
        self.dialog.scroll_layout.insertWidget(target_index, editor)
        if self.dialog.status_editor is not None:
            self.dialog.status_editor.move_item(source_index, target_index)
        self.dialog.schedule_resize_to_content()
