import pytest
import tempfile
from pathlib import Path
from unittest import mock
from Navigation_Bot.core.json_store import JsonStore

class TestJsonStore:

    def test_replace_failure_preserves_original_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'data.json'
            target.write_text('{"value": "original"}', encoding='utf-8')
            store = JsonStore(log_func=lambda *_: None)
            with mock.patch('Navigation_Bot.core.json_store.os.replace', side_effect=OSError('replace failed')):
                with pytest.raises(OSError):
                    store.save_in_json({'value': 'new'}, target)
            assert target.read_text(encoding='utf-8') == '{"value": "original"}'
            assert list(Path(directory).glob('*.tmp')) == []

    def test_successful_save_removes_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'data.json'
            target.write_text('{"value": "original"}', encoding='utf-8')
            JsonStore(log_func=lambda *_: None).save_in_json({'value': 'new'}, target)
            assert '"new"' in target.read_text(encoding='utf-8')
            assert not target.with_suffix('.json.backup').exists()
