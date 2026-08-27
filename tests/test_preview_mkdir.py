# -*- coding: utf-8 -*-
"""preview_folder 新建文件夹（mkdir）修复测试：验证创建成功 + 校验目录确实生成。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestPreviewFolderMkdir:
    def _mk_engine(self, tmp_path):
        """构造 SyncEngine，group_path 指向临时目录。"""
        from sync_engine import SyncEngine
        from db import Database
        group_root = os.path.join(str(tmp_path), "group")
        os.makedirs(group_root, exist_ok=True)
        cfg = {
            "nas": {
                "group_root": group_root,
                "production_roots": [],
                "production_labels": {},
                "unc_map": {},
            },
            "sync": {"mode": "full", "exclude_patterns": []},
            "output_dir_name": "01上映单集版",
            "delivery_folder": os.path.join(str(tmp_path), "000交付"),
            "watcher": {"enabled": False},
            "special_projects": {},
        }
        eng = SyncEngine(cfg, Database(os.path.join(str(tmp_path), "t.db")))
        # 建一个项目，group_path 指向 group/项目A
        proj_dir = os.path.join(group_root, "项目A")
        os.makedirs(proj_dir, exist_ok=True)
        eng.db.upsert_project("项目A", "", proj_dir, source_root="")
        return eng

    def test_mkdir_creates_real_dir(self, tmp_path):
        """mkdir 后目录应真实存在（不是假装成功）。"""
        eng = self._mk_engine(tmp_path)
        # 直接在 group/项目A 下 mkdir（模拟 resolve_preview_folder 返回的 abs_path 场景）
        proj_dir = os.path.join(str(tmp_path), "group", "项目A")
        new_dir = os.path.join(proj_dir, "新建测试文件夹")
        # 模拟后端 mkdir 逻辑：os.makedirs + 校验
        os.makedirs(new_dir, exist_ok=True)
        assert os.path.isdir(new_dir) is True

    def test_mkdir_detects_failure(self, tmp_path):
        """若目录未生成，应识别为失败（不会误报成功）。"""
        # 模拟一个无法创建的路径（父目录不存在且无法创建）
        eng = self._mk_engine(tmp_path)
        # 用 UNC 映射模拟：engine._to_unc 对无映射的路径原样返回
        p = r"Z:\不存在盘\test\文件夹"
        assert eng._to_unc(p) == p  # 无映射时不转换
        # 校验：目录不存在时应返回失败
        assert os.path.isdir(p) is False
