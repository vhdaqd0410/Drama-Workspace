# -*- coding: utf-8 -*-
"""核心单元测试：统计口径、目录查找、交付路径计算。"""
import os
import sys
import shutil
import tempfile
import pytest

from scan import (
    compute_overview_stats,
    _is_active_project,
    _is_producing,
    find_dir_recursive,
)

# ============================================================
# 1. 统一统计口径（compute_overview_stats）
# ============================================================

class TestOverviewStats:
    def _sample(self, now="2026-08"):
        """构造三组测试数据。"""
        production = [
            {"name": "制作部A", "custom_status": "剪辑中", "delivery_status": "pending",
             "total_episodes": 20, "project_month": now},
            {"name": "空壳X", "custom_status": "", "delivery_status": "pending",
             "total_episodes": 0, "project_month": now},
        ]
        group_all = [
            {"name": "组A", "custom_status": "分集中", "delivery_status": "pending",
             "total_episodes": 70, "project_month": now},
            {"name": "组B", "custom_status": "审核中", "delivery_status": "pending",
             "total_episodes": 70, "project_month": now},
            {"name": "组C", "custom_status": "修改中", "delivery_status": "pending",
             "total_episodes": 70, "project_month": now},
        ]
        group_completed = [
            {"name": "完成A", "custom_status": "已完成", "delivery_status": "delivered",
             "total_episodes": 70, "project_month": now},
            {"name": "完成B", "custom_status": "已完成", "delivery_status": "delivered",
             "total_episodes": 70, "project_month": now},
            {"name": "上月完成", "custom_status": "已完成", "delivery_status": "delivered",
             "total_episodes": 70, "project_month": "2026-07"},
        ]
        return production, group_all, group_completed

    def test_identity_holds(self):
        """恒等式：本月项目 = 本月已完成 + 制作中。"""
        p, g, c = self._sample()
        s = compute_overview_stats(p, g, c, now_month="2026-08")
        assert s["this_month"] == s["this_month_done"] + s["producing"]
        assert s["this_month"] == 6   # 制作部A + 3组 + 2完成
        assert s["this_month_done"] == 2
        assert s["producing"] == 4     # 制作部A + 组A(分集中) + 组B + 组C

    def test_total_excludes_shell(self):
        """总项目排除空壳，但包含上月已完成。"""
        p, g, c = self._sample()
        s = compute_overview_stats(p, g, c, now_month="2026-08")
        assert s["total"] == 7  # 排除空壳X，包含上月完成

    def test_producing_includes_fenji(self):
        """制作中应包含'分集中'状态。"""
        p, g, c = self._sample()
        s = compute_overview_stats(p, g, c, now_month="2026-08")
        assert s["producing"] == 4  # 含组A(分集中)

    def test_empty(self):
        s = compute_overview_stats([], [], [])
        assert s["total"] == 0 and s["this_month"] == 0


# ============================================================
# 2. 目录查找（find_dir_recursive）
# ============================================================

class TestFindDirRecursive:
    def test_finds_nested(self, tmp_path):
        root = tmp_path / "proj"
        (root / "04 多版本交片" / "01上映单集版").mkdir(parents=True)
        dirs = find_dir_recursive(str(root), "01上映单集版")
        assert len(dirs) == 1
        assert dirs[0].endswith("01上映单集版")

    def test_multiple(self, tmp_path):
        root = tmp_path / "proj"
        (root / "a" / "01上映单集版").mkdir(parents=True)
        (root / "b" / "01上映单集版").mkdir(parents=True)
        dirs = find_dir_recursive(str(root), "01上映单集版")
        assert len(dirs) == 2

    def test_not_found(self, tmp_path):
        assert find_dir_recursive(str(tmp_path), "不存在") == []


# ============================================================
# 4. 交付路径计算（SyncEngine.deliver_to_production 的前置校验）
# ============================================================

class TestDeliverPath:
    def _mk_project(self, engine, name, with_delivery=True):
        """在临时 group/prod 下建项目，写入 DB，返回 (group_path, prod_path, src)。"""
        from sync_engine import SyncEngine
        group_root = engine.nas["group_root"]
        prod_root = engine.nas["production_roots"][0]
        os.makedirs(group_root, exist_ok=True)
        os.makedirs(prod_root, exist_ok=True)
        gp = os.path.join(group_root, name)
        pp = os.path.join(prod_root, name)
        os.makedirs(gp, exist_ok=True)
        os.makedirs(pp, exist_ok=True)
        engine.db.upsert_project(name, pp, gp, source_root=prod_root)
        if with_delivery:
            d = os.path.join(gp, "000交付")
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "1.mp4"), "w").write("x")
        return gp, pp

    def test_no_project(self, engine):
        ok, msg = engine.deliver_to_production("不存在的项目")
        assert not ok and "项目不存在" in msg

    def test_no_prod_path(self, engine, tmp_db):
        """无 production_path 时报错。"""
        gp = os.path.join(engine.nas["group_root"], "X")
        os.makedirs(gp, exist_ok=True)
        # 只 upsert group（production_path 为空）
        engine.db.upsert_project("X", "", gp, source_root="")
        ok, msg = engine.deliver_to_production("X")
        assert not ok and "制作部" in msg

    def test_src_not_exist(self, engine):
        """组内无000交付时报错。"""
        gp, pp = self._mk_project(engine, "无交付", with_delivery=False)
        ok, msg = engine.deliver_to_production("无交付")
        assert not ok and "000交付" in msg

    def test_find_output_dirs_persist(self, engine, tmp_db):
        """上映单集版查找 + 持久化缓存。"""
        gp, pp = self._mk_project(engine, "有上映单集版")
        out = os.path.join(gp, "04", "01上映单集版")
        os.makedirs(out, exist_ok=True)
        dirs = engine._find_output_dirs(gp, "有上映单集版")
        assert dirs and dirs[0].endswith("01上映单集版")
        # 缓存已写盘
        assert os.path.isfile(engine._output_dir_cache_file)

    def test_cache_invalidates_on_missing(self, engine, tmp_db):
        """缓存的路径失效后重新扫描。"""
        gp, pp = self._mk_project(engine, "失效项目")
        out = os.path.join(gp, "01上映单集版")
        os.makedirs(out, exist_ok=True)
        dirs = engine._find_output_dirs(gp, "失效项目")
        assert len(dirs) == 1
        shutil.rmtree(out)
        dirs2 = engine._find_output_dirs(gp, "失效项目")
        assert dirs2 == []


# ============================================================
# 5. 质检自动流转（QAEngine._auto_advance_workflow）
# ============================================================

class TestQAWorkflow:
    def _mk_project(self, engine, name, status="待质检"):
        gp = os.path.join(engine.nas["group_root"], name)
        os.makedirs(gp, exist_ok=True)
        engine.db.upsert_project(name, "", gp, source_root="")
        engine.db.update_project_status(name, custom_status=status)
        return name

    def _qa_engine_with_db(self, tmp_db, monkeypatch):
        """构造 QAEngine，并把它的全局 db 换成临时 db。"""
        import qa_engine as qa_mod
        engine = qa_mod.QAEngine()
        monkeypatch.setattr(qa_mod, "db", tmp_db)
        return engine

    def test_pass_goes_pending(self, engine, tmp_db, monkeypatch):
        name = self._mk_project(engine, "通过项目", status="待质检")
        qa = self._qa_engine_with_db(tmp_db, monkeypatch)
        qa._auto_advance_workflow(name, passed=10, failed=0)
        p = tmp_db.get_project(name)
        assert p["custom_status"] == "待交付"

    def test_fail_goes_revising(self, engine, tmp_db, monkeypatch):
        name = self._mk_project(engine, "失败项目", status="质检中")
        qa = self._qa_engine_with_db(tmp_db, monkeypatch)
        qa._auto_advance_workflow(name, passed=5, failed=3)
        p = tmp_db.get_project(name)
        assert p["custom_status"] == "修改中"

    def test_non_qa_status_not_changed(self, engine, tmp_db, monkeypatch):
        """非质检中/待质检状态不被自动流转覆盖。"""
        name = self._mk_project(engine, "剪辑中项目", status="剪辑中")
        qa = self._qa_engine_with_db(tmp_db, monkeypatch)
        qa._auto_advance_workflow(name, passed=10, failed=0)
        p = tmp_db.get_project(name)
        assert p["custom_status"] == "剪辑中"
