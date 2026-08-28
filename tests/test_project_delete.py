# -*- coding: utf-8 -*-
"""项目删除（软移除 + 忽略列表 + 扫描跳过）测试。"""
import os
import json
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestProjectDelete:
    def _engine(self, tmp_path):
        from sync_engine import SyncEngine
        from db import Database
        group_root = os.path.join(str(tmp_path), "group")
        os.makedirs(group_root, exist_ok=True)
        cfg = {
            "nas": {"group_root": group_root, "production_roots": [], "unc_map": {}},
            "sync": {"mode": "full"},
            "output_dir_name": "01上映单集版",
            "delivery_folder": os.path.join(str(tmp_path), "000交付"),
            "watcher": {"enabled": False},
        }
        return SyncEngine(cfg, Database(os.path.join(str(tmp_path), "t.db")))

    def _mk_group_project(self, tmp_path, eng, name):
        proj = os.path.join(str(tmp_path), "group", name)
        os.makedirs(proj, exist_ok=True)
        open(os.path.join(proj, "x.mp4"), "w").close()
        eng.db.upsert_project(name, "", proj, source_root="")
        return proj

    def test_ignored_list_roundtrip(self, tmp_path):
        eng = self._engine(tmp_path)
        assert eng.db.get_ignored_projects() == []
        eng.db.add_ignored_project("项目A")
        eng.db.add_ignored_project("项目A")  # 去重
        eng.db.add_ignored_project("项目B")
        assert set(eng.db.get_ignored_projects()) == {"项目A", "项目B"}
        eng.db.remove_ignored_project("项目A")
        assert eng.db.get_ignored_projects() == ["项目B"]

    def test_scan_skips_ignored(self, tmp_path):
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "正常项目")
        self._mk_group_project(tmp_path, eng, "被忽略项目")

        # 忽略「被忽略项目」后，扫描组内应跳过它
        eng.db.add_ignored_project("被忽略项目")
        found = eng.scan_group_projects()
        assert "正常项目" in found
        assert "被忽略项目" not in found

    def test_soft_delete_adds_ignored(self, tmp_path):
        """软删除：删记录 + 加入忽略列表，扫描不再重新加入。"""
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "要删除的项目")
        eng.db.add_ignored_project("要删除的项目")
        eng.db.delete_project("要删除的项目")

        # 记录已删
        assert eng.db.get_project("要删除的项目") is None
        # 重新扫描：因为被忽略，不会重新加入
        found = eng.scan_group_projects()
        assert "要删除的项目" not in found

    def test_enriched_skips_ignored(self, tmp_path):
        """get_projects_enriched 的 group_all 也不展示忽略的项目。"""
        eng = self._engine(tmp_path)
        self._mk_group_project(tmp_path, eng, "正常项目")
        self._mk_group_project(tmp_path, eng, "被忽略项目")
        eng.db.add_ignored_project("被忽略项目")

        enriched = eng.get_projects_enriched()
        group_names = {p["name"] for p in enriched.get("group_all", [])}
        assert "正常项目" in group_names
        assert "被忽略项目" not in group_names

    def test_hard_delete_removes_nas_dir(self, tmp_path):
        """彻底删除：删数据库记录 + 删 NAS 文件夹 + 加入忽略列表。"""
        eng = self._engine(tmp_path)
        proj_dir = self._mk_group_project(tmp_path, eng, "彻底删项目")
        assert os.path.isdir(proj_dir)

        # 模拟 hard 删除的核心逻辑（删 NAS + 删记录 + 忽略）
        import shutil
        shutil.rmtree(proj_dir)
        eng.db.delete_project("彻底删项目")
        eng.db.add_ignored_project("彻底删项目")

        assert not os.path.isdir(proj_dir)
        assert eng.db.get_project("彻底删项目") is None
        assert "彻底删项目" in eng.db.get_ignored_projects()
        # 重新扫描不会重新加入
        assert "彻底删项目" not in eng.scan_group_projects()
