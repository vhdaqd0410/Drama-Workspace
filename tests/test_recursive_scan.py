# -*- coding: utf-8 -*-
"""递归扫描测试：验证项目在子文件夹时能正确识别（如漫剧七部：分类→项目）。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _mk_tree(base, rel_paths):
    """在 base 下创建目录树。rel_paths: [相对路径, ...]"""
    for rel in rel_paths:
        os.makedirs(os.path.join(base, rel), exist_ok=True)


class TestRecursiveScan:
    def _make_engine_with_root(self, tmp_path, root_subdir, depth):
        """构造 SyncEngine，production_roots 指向 tmp/root_subdir，并配置递归深度。"""
        from sync_engine import SyncEngine
        from db import Database
        root = os.path.join(str(tmp_path), root_subdir)
        os.makedirs(root, exist_ok=True)
        cfg = {
            "nas": {
                "group_root": os.path.join(str(tmp_path), "group"),
                "production_roots": [root],
                "production_labels": {root: "七部"},
                "production_roots_config": {root: {"recursive_depth": depth}},
                "unc_map": {},
            },
            "sync": {"mode": "full", "exclude_patterns": []},
            "output_dir_name": "01上映单集版",
            "delivery_folder": os.path.join(str(tmp_path), "000交付"),
            "watcher": {"enabled": False, "stable_seconds": 30, "extensions": [".mp4"]},
            "special_projects": {},
        }
        os.makedirs(cfg["nas"]["group_root"], exist_ok=True)
        eng = SyncEngine(cfg, Database(os.path.join(str(tmp_path), "t.db")))
        return eng, root

    def test_recursive_nested_projects(self, tmp_path):
        """分类目录 → 项目 的嵌套结构应全部识别。"""
        eng, root = self._make_engine_with_root(tmp_path, "seven", 3)
        _mk_tree(root, [
            "DK类/00_10018_项目A",
            "DK类/00_10045_项目B",
            "恐怖片/00_20001_项目C",
            "恐怖片/00_20002_项目D",
        ])
        names = eng.scan_projects()
        # 应识别 4 个带编号的项目
        assert "00_10018_项目A" in names
        assert "00_10045_项目B" in names
        assert "00_20001_项目C" in names
        assert "00_20002_项目D" in names
        assert len(names) == 4

    def test_direct_projects(self, tmp_path):
        """根目录第一层就是项目的结构（无递归）也应识别。"""
        eng, root = self._make_engine_with_root(tmp_path, "direct", 3)
        _mk_tree(root, ["项目X", "项目Y", "项目Z"])
        # 这些名字不带编号，且无项目结构 → 递归时不会误判为项目
        # 但为兼容直接结构，也应识别（用 _looks_like_project 需带编号或结构）
        # 这里用带编号的名称验证直接结构
        _mk_tree(root, ["10001_项目X", "10002_项目Y"])
        names = eng.scan_projects()
        assert "10001_项目X" in names
        assert "10002_项目Y" in names

    def test_recursive_zero_only_first_level(self, tmp_path):
        """recursive_depth=0：只扫第一层，不递归到分类子目录。"""
        eng, root = self._make_engine_with_root(tmp_path, "flat", 0)
        _mk_tree(root, ["DK类/00_10018_项目A", "00_50001_顶层项目"])
        names = eng.scan_projects()
        # 只识别顶层项目（带编号），不递归进 DK类
        assert "00_50001_顶层项目" in names
        assert "00_10018_项目A" not in names

    def test_skips_template_and_system_dirs(self, tmp_path):
        """跳过模板/00_id_ 等非项目目录。"""
        eng, root = self._make_engine_with_root(tmp_path, "mix", 3)
        _mk_tree(root, [
            "DK类/00_10018_项目A",
            "模板",                 # 分类词 → 跳过
            "00_id_占位",           # 系统目录 → 跳过
            "存档/旧项目",          # 分类词 → 跳过
        ])
        names = eng.scan_projects()
        assert "00_10018_项目A" in names
        assert "模板" not in names
        assert "00_id_占位" not in names
        assert "旧项目" not in names

    def test_project_with_struct_subdir(self, tmp_path):
        """无编号但含项目结构子目录的，也应识别为项目。"""
        eng, root = self._make_engine_with_root(tmp_path, "struct", 3)
        # 无编号但含 01上映单集版 结构
        proj = os.path.join(root, "某个无编号项目")
        _mk_tree(root, ["某个无编号项目/01上映单集版"])
        names = eng.scan_projects()
        assert "某个无编号项目" in names
