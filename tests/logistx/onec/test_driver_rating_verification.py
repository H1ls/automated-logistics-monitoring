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

class TestDriverRatingTableReader:

    def test_parses_kind_and_hours_from_ocr_rows(self):
        snapshot = DriverRatingTableReader.parse_lines([(25, 'N Дата Вид Оценка водителя'), (55, '1 21.06.2026 13:36 Простой на погрузке 7 ч.'), (76, '2 21.06.2026 13:36 Простой на разгрузке 12 ч.')])
        assert [row.key for row in snapshot.rows] == [('Простой на погрузке', 7), ('Простой на разгрузке', 12)]

    def test_keeps_unknown_data_row_so_it_can_be_deleted(self):
        snapshot = DriverRatingTableReader.parse_lines([(55, '1 21.06.2026 13:36 Неверный вид 9 ч.')])
        assert len(snapshot.rows) == 1
        assert snapshot.rows[0].kind == '__unknown__'

    def test_ignores_unknown_ocr_noise_without_hours(self):
        snapshot = DriverRatingTableReader.parse_lines([(55, '1 04.07.2026 9:16:00 Без отклонений'), (76, '1 04.07.2026 9:16:00 ях')])
        assert [row.key for row in snapshot.rows] == [('Без отклонений', 0)]

class _Snapshots:

    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)

    def read(self, _path):
        return next(self.snapshots)

class TestDriverRatingRepair:

    def test_deletes_wrong_hours_and_adds_expected_row_again(self):
        wrong = RatingRow('Простой на погрузке', 8, 55, 'wrong 8 h')
        correct = RatingRow('Простой на погрузке', 7, 55, 'correct 7 h')
        step = DriverRatingStep.__new__(DriverRatingStep)
        step.verify_attempts = 3
        step.table_reader = _Snapshots([RatingTableSnapshot(rows=(wrong,), recognized_text='wrong'), RatingTableSnapshot(rows=(correct,), recognized_text='correct')])
        step.session = SimpleNamespace(sleep=lambda _seconds: None)
        step.log = lambda *_: None
        step._capture_rating_table = lambda: 'table.png'
        deleted = []
        added = []
        step._delete_rating_row = deleted.append
        step._add_expected_row = added.append
        ctx = SimpleNamespace(state={})
        step._verify_and_repair(ctx, [{'kind': 'Простой на погрузке', 'hours': 7}])
        assert deleted == [wrong]
        assert added == [('Простой на погрузке', 7)]
        assert ctx.state['driver_rating_verification']['ok']
