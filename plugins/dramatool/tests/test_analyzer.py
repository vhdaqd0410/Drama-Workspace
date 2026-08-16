from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.analyzer import build_rename_plan


class SplitDirTests(unittest.TestCase):
    """测试 split_source_dir 参数的各种场景。"""

    def test_no_split_dir_behaves_normally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "01.mp4").write_bytes(b"a")
            (tmp / "02.mp4").write_bytes(b"b")

            plan = build_rename_plan(tmp, split_source_dir=None)

            self.assertEqual(len(plan), 2)
            self.assertEqual([i.target.name for i in plan], ["01.mp4", "02.mp4"])

    def test_flat_folder_split_dir_merges(self) -> None:
        """单层目录 + 拆集目录（拆集文件直接在拆集根目录下）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            main_dir = tmp / "成片"
            main_dir.mkdir()
            for i in range(1, 7):
                (main_dir / f"{i:02d}.mp4").write_bytes(b"x")

            split_dir = tmp / "拆集"
            split_dir.mkdir()
            (split_dir / "02-1.mp4").write_bytes(b"s1")
            (split_dir / "02-2.mp4").write_bytes(b"s2")
            (split_dir / "05-1.mp4").write_bytes(b"s3")
            (split_dir / "05-2.mp4").write_bytes(b"s4")

            plan = build_rename_plan(main_dir, split_source_dir=split_dir)

            # 01, 02-1, 02-2, 03, 04, 05-1, 05-2, 06 → 8 files
            self.assertEqual(len(plan), 8)
            self.assertEqual(
                [i.target.name for i in plan],
                ["01.mp4", "02.mp4", "03.mp4", "04.mp4", "05.mp4", "06.mp4", "07.mp4", "08.mp4"],
            )
            # 原 02 和 05 被替换
            self.assertNotIn((main_dir / "02.mp4"), [i.source for i in plan])
            self.assertNotIn((main_dir / "05.mp4"), [i.source for i in plan])

    def test_split_dir_mirrors_version_folders(self) -> None:
        """拆集目录镜像了原始目录的版本子目录结构。

        000交付/                  拆集/
        ├── 成片/                 ├── 成片/
        │   ├── 01.mp4            │   ├── 02-1.mp4
        │   ├── 02.mp4            │   └── 02-2.mp4
        │   └── 03.mp4            └── 00成片/
        └── 00成片/                   └── 03-1.mp4
            ├── 01.mp4
            ├── 02.mp4
            └── 03.mp4
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            delivery = Path(tmpdir) / "000交付"
            delivery.mkdir()

            v1 = delivery / "成片"
            v1.mkdir()
            for i in range(1, 4):
                (v1 / f"{i:02d}.mp4").write_bytes(b"v1")

            v2 = delivery / "00成片"
            v2.mkdir()
            for i in range(1, 4):
                (v2 / f"{i:02d}.mp4").write_bytes(b"v2")

            split_root = Path(tmpdir) / "拆集"
            split_root.mkdir()
            s1 = split_root / "成片"
            s1.mkdir()
            (s1 / "02-1.mp4").write_bytes(b"s1")
            (s1 / "02-2.mp4").write_bytes(b"s2")

            s2 = split_root / "00成片"
            s2.mkdir()
            (s2 / "03-1.mp4").write_bytes(b"s3")

            plan = build_rename_plan(delivery, split_source_dir=split_root)

            # 成片: 01, 02-1, 02-2, 03 → 4 files
            # 00成片: 01, 02, 03-1 → 3 files
            # Total: 7 files
            self.assertEqual(len(plan), 7)

            # 按版本分组验证
            v1_items = [i for i in plan if "成片" in str(i.target.parent) and "00成片" not in str(i.target.parent)]
            self.assertEqual(len(v1_items), 4)
            self.assertEqual([i.target.name for i in v1_items], ["01.mp4", "02.mp4", "03.mp4", "04.mp4"])
            # 成片的 02.mp4 被替换
            self.assertNotIn((v1 / "02.mp4"), [i.source for i in v1_items])
            self.assertIn((s1 / "02-1.mp4"), [i.source for i in v1_items])

            v2_items = [i for i in plan if "00成片" in str(i.target.parent)]
            self.assertEqual(len(v2_items), 3)
            self.assertEqual([i.target.name for i in v2_items], ["01.mp4", "02.mp4", "03.mp4"])
            # 00成片的 03.mp4 被替换
            self.assertNotIn((v2 / "03.mp4"), [i.source for i in v2_items])
            self.assertIn((s2 / "03-1.mp4"), [i.source for i in v2_items])

    def test_split_dir_with_only_splits_no_originals(self) -> None:
        """拆集目录中的集数在原始目录中没有对应文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            main_dir = tmp / "成片"
            main_dir.mkdir()
            (main_dir / "01.mp4").write_bytes(b"a")
            (main_dir / "03.mp4").write_bytes(b"c")

            split_dir = tmp / "拆集"
            split_dir.mkdir()
            (split_dir / "02-1.mp4").write_bytes(b"s1")
            (split_dir / "02-2.mp4").write_bytes(b"s2")

            plan = build_rename_plan(main_dir, split_source_dir=split_dir)

            self.assertEqual(len(plan), 4)
            self.assertEqual([i.target.name for i in plan], ["01.mp4", "02.mp4", "03.mp4", "04.mp4"])


if __name__ == "__main__":
    unittest.main()
