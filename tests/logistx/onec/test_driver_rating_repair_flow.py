import pytest
import sys
from types import SimpleNamespace
sys.modules.setdefault('pytesseract', SimpleNamespace(Output=SimpleNamespace(DICT='dict')))
_pil_image = SimpleNamespace()
_pil_image_ops = SimpleNamespace()
_pil_image_draw = SimpleNamespace()
sys.modules.setdefault('PIL', SimpleNamespace(Image=_pil_image, ImageOps=_pil_image_ops, ImageDraw=_pil_image_draw))
sys.modules.setdefault('PIL.Image', _pil_image)
sys.modules.setdefault('PIL.ImageOps', _pil_image_ops)
sys.modules.setdefault('PIL.ImageDraw', _pil_image_draw)
from LogistX.onec.driver_rating_table import DriverRatingTableReader, RatingRow, RatingTableSnapshot
from LogistX.onec.steps.driver_rating import DriverRatingStep

class _Snapshots:

    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)

    def read(self, _path):
        return next(self.snapshots)

class TestDriverRatingRepairFlow:

    def _make_step(self, snapshots):
        step = DriverRatingStep.__new__(DriverRatingStep)
        step.verify_attempts = 3
        step.table_reader = _Snapshots(snapshots)
        step.session = SimpleNamespace(sleep=lambda _seconds: None)
        step.log = lambda *_: None
        step._capture_rating_table = lambda: 'table.png'
        deleted = []
        added = []
        step._delete_rating_row = deleted.append
        step._add_expected_row = added.append
        return (step, deleted, added)

    def test_does_not_add_when_expected_row_already_exists(self):
        correct = RatingRow('test', 7, 55, 'correct 7 h')
        step, deleted, added = self._make_step([RatingTableSnapshot(rows=(correct,), recognized_text='correct')])
        ctx = SimpleNamespace(state={})
        step._verify_and_repair(ctx, [{'kind': 'test', 'hours': 7}])
        assert deleted == []
        assert added == []
        assert ctx.state['driver_rating_verification']['ok']

    def test_deletes_duplicate_expected_row_without_readding_it(self):
        first = RatingRow('test', 7, 55, 'correct 7 h')
        duplicate = RatingRow('test', 7, 76, 'duplicate 7 h')
        step, deleted, added = self._make_step([RatingTableSnapshot(rows=(first, duplicate), recognized_text='duplicate'), RatingTableSnapshot(rows=(first,), recognized_text='correct')])
        ctx = SimpleNamespace(state={})
        step._verify_and_repair(ctx, [{'kind': 'test', 'hours': 7}])
        assert deleted == [duplicate]
        assert added == []
        assert ctx.state['driver_rating_verification']['ok']

    def test_raises_when_missing_row_does_not_appear_after_repair(self):
        step, deleted, added = self._make_step([RatingTableSnapshot(rows=(), recognized_text='header'), RatingTableSnapshot(rows=(), recognized_text='header')])
        ctx = SimpleNamespace(state={})
        with pytest.raises(RuntimeError):
            step._verify_and_repair(ctx, [{'kind': 'test', 'hours': 7}])
        assert deleted == []
        assert added == [('test', 7)]

    def test_accepts_expected_kind_when_hours_are_not_recognized(self):
        unconfirmed = RatingRow('test', 0, 55, '1 29.06.2026 8:09:37 test')
        step, deleted, added = self._make_step([RatingTableSnapshot(rows=(unconfirmed,), recognized_text='header\ntest')])
        ctx = SimpleNamespace(state={})
        step._verify_and_repair(ctx, [{'kind': 'test', 'hours': 7}])
        assert deleted == []
        assert added == []
        assert ctx.state['driver_rating_verification']['ok']
        assert ctx.state['driver_rating_verification']['actual'] == [('test', 7)]

    def test_accepts_mixed_confirmed_and_unconfirmed_expected_rows(self):
        confirmed = RatingRow('late', 7, 55, '1 29.06.2026 8:09:37 late 7 h')
        unconfirmed = RatingRow('idle', 0, 76, '2 29.06.2026 8:09:37 idle')
        step, deleted, added = self._make_step([RatingTableSnapshot(rows=(confirmed, unconfirmed), recognized_text='late 7\nidle')])
        ctx = SimpleNamespace(state={})
        step._verify_and_repair(ctx, [{'kind': 'late', 'hours': 7}, {'kind': 'idle', 'hours': 5}])
        assert deleted == []
        assert added == []
        assert ctx.state['driver_rating_verification']['ok']

class TestDriverRatingTableReaderFlow:

    def test_ignores_table_header(self):
        snapshot = DriverRatingTableReader.parse_lines([(25, 'N | Дата | Вид | Оценка водителя | Начало отклонения | Окончан'), (55, '1 29.06.2026 08:09:37 test 7 ч.')])
        assert [row.key for row in snapshot.rows] == [('__unknown__', 7)]
