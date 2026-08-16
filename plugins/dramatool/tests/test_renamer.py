import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.analyzer import build_rename_plan, infer_episode_number
from ui.main_window import build_progress_text, next_pause_state
from utils.fileutil import parse_dropped_path


class RenamePlanTests(unittest.TestCase):
    def test_infer_episode_number_from_chinese_format(self) -> None:
        self.assertEqual(infer_episode_number("第12集.mp4"), 12)
        self.assertEqual(infer_episode_number("第3集.mkv"), 3)

    def test_infer_episode_number_from_plain_numeric_format(self) -> None:
        self.assertEqual(infer_episode_number("01.mp4"), 1)
        self.assertEqual(infer_episode_number("S01E02.mkv"), 2)

    def test_infer_episode_number_from_common_variants(self) -> None:
        self.assertEqual(infer_episode_number("第 03 集.mkv"), 3)
        self.assertEqual(infer_episode_number("EP01.mp4"), 1)

    def test_build_rename_plan_renames_files_in_same_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "1集.mp4").write_bytes(b"a")
            (tmp_path / "2集.mkv").write_bytes(b"b")

            plan = build_rename_plan(tmp_path)

            self.assertEqual(len(plan), 2)
            self.assertEqual(plan[0].target.name, "01.mp4")
            self.assertEqual(plan[1].target.name, "02.mkv")
            self.assertTrue(plan[0].source.exists())
            self.assertTrue(plan[0].target.parent.exists())
            self.assertIn(tmp_path.name + "_renamed", str(plan[0].target))

    def test_build_rename_plan_groups_multiple_versions_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            version_one = tmp_path / "00成片"
            version_two = tmp_path / "1.有音乐无字幕版本"
            version_one.mkdir(parents=True)
            version_two.mkdir(parents=True)
            (version_one / "1集.mp4").write_bytes(b"a")
            (version_two / "2集.mp4").write_bytes(b"b")

            plan = build_rename_plan(tmp_path)

            self.assertEqual(len(plan), 2)
            self.assertIn(tmp_path.name + "_renamed", str(plan[0].target))
            self.assertEqual(plan[0].target.name, "01.mp4")
            self.assertEqual(plan[1].target.name, "01.mp4")

    def test_build_rename_plan_uses_custom_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "custom_output"
            (tmp_path / "1集.mp4").write_bytes(b"a")

            plan = build_rename_plan(tmp_path, output_dir=output_dir)

            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0].target.parent, output_dir)
            self.assertEqual(plan[0].target.name, "01.mp4")

    def test_build_rename_plan_merges_split_and_unsplit_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            full_dir = tmp_path / "成片"
            split_dir = tmp_path / "拆集"
            full_dir.mkdir(parents=True)
            split_dir.mkdir(parents=True)
            (full_dir / "1集.mp4").write_bytes(b"a")
            (full_dir / "2集.mp4").write_bytes(b"b")
            (full_dir / "3集.mp4").write_bytes(b"c")
            (split_dir / "2-1.mp4").write_bytes(b"d")
            (split_dir / "2-2.mp4").write_bytes(b"e")

            plan = build_rename_plan(tmp_path)

            self.assertEqual(len(plan), 4)
            self.assertEqual([item.target.name for item in plan], ["01.mp4", "02.mp4", "03.mp4", "04.mp4"])
            self.assertNotIn(full_dir / "2集.mp4", [item.source for item in plan])

    def test_build_rename_plan_merges_nested_split_overlay_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            delivery_dir = tmp_path / "000交付"
            split_dir = delivery_dir / "拆集后"
            version_dir = delivery_dir / "成片"
            split_version_dir = split_dir / "成片"
            version_dir.mkdir(parents=True)
            split_version_dir.mkdir(parents=True)
            (version_dir / "1集.mp4").write_bytes(b"a")
            (version_dir / "2集.mp4").write_bytes(b"b")
            (version_dir / "3集.mp4").write_bytes(b"c")
            (split_version_dir / "2-1.mp4").write_bytes(b"d")
            (split_version_dir / "2-2.mp4").write_bytes(b"e")

            plan = build_rename_plan(delivery_dir)

            self.assertEqual(len(plan), 4)
            self.assertEqual([item.target.name for item in plan], ["01.mp4", "02.mp4", "03.mp4", "04.mp4"])
            self.assertIn(split_version_dir / "2-1.mp4", [item.source for item in plan])
            self.assertIn(split_version_dir / "2-2.mp4", [item.source for item in plan])
            self.assertNotIn(version_dir / "2集.mp4", [item.source for item in plan])

    def test_next_pause_state_toggles_between_pause_and_resume(self) -> None:
        paused, label = next_pause_state(False)
        self.assertTrue(paused)
        self.assertEqual(label, "继续")

        paused, label = next_pause_state(True)
        self.assertFalse(paused)
        self.assertEqual(label, "暂停")

    def test_build_progress_text_formats_progress(self) -> None:
        self.assertEqual(build_progress_text(3, 10), "已完成 3/10 个文件 (30.0%)")
        self.assertEqual(build_progress_text(0, 0), "已完成 0/0 个文件")

    def test_parse_dropped_path_supports_existing_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            self.assertEqual(parse_dropped_path(str(temp_path)), temp_path)

    def test_parse_dropped_path_returns_none_for_missing_path(self) -> None:
        self.assertIsNone(parse_dropped_path("C:/this/path/does/not/exist"))


if __name__ == "__main__":
    unittest.main()
