import json
import tempfile
from pathlib import Path
from LogistX.onec.uimap import UiMap

class TestUiMapScaling:

    def _map(self, directory: str) -> UiMap:
        path = Path(directory) / 'ui.json'
        path.write_text(json.dumps({'reference_screen': [1920, 1080], 'anchors': {'point': [100, 200]}, 'regions': {'region': [10, 20, 300, 400]}, 'offsets': {'offset': [-20, 30]}}), encoding='utf-8')
        return UiMap(path)

    def test_scales_coordinates_to_runtime_viewport(self):
        with tempfile.TemporaryDirectory() as directory:
            ui_map = self._map(directory)
            ui_map.set_viewport(3840, 2160)
            assert ui_map.get_anchor('point') == (200, 400)
            assert ui_map.get_region('region') == (20, 40, 600, 800)
            assert ui_map.get_offset('offset') == (-40, 60)

    def test_stores_runtime_anchor_in_reference_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            ui_map = self._map(directory)
            ui_map.set_viewport(3840, 2160)
            ui_map.set_anchor('new', 400, 600)
            ui_map.save()
            stored = json.loads(ui_map.path.read_text(encoding='utf-8'))
            assert stored['anchors']['new'] == [200, 300]
