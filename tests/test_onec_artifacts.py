from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image

from LogistX.onec.artifacts import OneCArtifacts


class _UiMap:
    def get_region(self, name):
        if name == "area":
            return 1, 2, 10, 12
        raise KeyError(name)


class _Session:
    def __init__(self, tmp_dir):
        self.tmp_dir = Path(tmp_dir)
        self.ui_map = _UiMap()
        self.captures = []

    def capture_full(self, filename):
        self.captures.append(("full", filename))
        path = self.tmp_dir / filename
        Image.new("RGB", (30, 30), "white").save(path)
        return path

    def capture_region(self, region_name, filename):
        self.captures.append(("region", region_name, filename))
        path = self.tmp_dir / filename
        Image.new("RGB", (30, 30), "white").save(path)
        return path


class OneCArtifactsTests(TestCase):
    def test_uses_standard_stage_and_artifact_filename(self):
        with TemporaryDirectory() as tmp:
            session = _Session(tmp)
            artifacts = OneCArtifacts(session)

            path = artifacts.capture_region("fill times", "cargo/search", "area")

            self.assertEqual(path.name, "fill_times__cargo_search.png")
            self.assertEqual(session.captures, [("region", "area", "fill_times__cargo_search.png")])

    def test_debug_only_capture_is_skipped_when_disabled(self):
        with TemporaryDirectory() as tmp:
            session = _Session(tmp)

            result = OneCArtifacts(session, enabled=False).capture_full("fill_times", "regions_source", debug_only=True)

            self.assertIsNone(result)
            self.assertEqual(session.captures, [])

    def test_annotations_are_created_only_in_debug_mode(self):
        with TemporaryDirectory() as tmp:
            session = _Session(tmp)
            source = session.capture_full("source.png")
            disabled = OneCArtifacts(session, enabled=False)
            enabled = OneCArtifacts(session, enabled=True, log_func=lambda *_: None)

            self.assertIsNone(disabled.annotate_points(source, "capture", "points", [("p", 5, 6)]))
            output = enabled.annotate_regions(source, "capture", "regions", ["area"])

            self.assertEqual(output.name, "capture__regions.png")
            self.assertTrue(output.exists())
