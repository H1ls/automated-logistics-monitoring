from __future__ import annotations

from collections.abc import Iterable

from Navigation_Bot.gui.dialogs.components.address_edit_models import AddressBlocksCodec
from Navigation_Bot.gui.widgets.address_point_editor import AddressPointEditor
from Navigation_Bot.gui.widgets.status_editor_widget import StatusEditorWidget


class AddressResultBuilder:
    def __init__(self, *, codec: AddressBlocksCodec, entries: Iterable[AddressPointEditor], status_editor: StatusEditorWidget | None):
        self.codec = codec
        self.entries = entries
        self.status_editor = status_editor

    def get_processed(self) -> list[bool] | None:
        if self.status_editor is None:
            return None
        return self.status_editor.get_processed()

    def build_result(self, comment: str) -> tuple[list[dict[str, str]], dict[str, str]]:
        entries = list(self.entries)
        points = [editor.to_draft() for editor in entries]
        blocks = self.codec.serialize(points, comment)
        metadata: dict[str, str] = {}
        for editor in entries:
            metadata.update(editor.metadata())
        return blocks, metadata
