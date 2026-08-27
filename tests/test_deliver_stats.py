# -*- coding: utf-8 -*-
"""deliver.py 交付完整性统计（get_delivery_stats）测试。

get_delivery_stats 扫描项目的 000交付 目录，统计成片/有音乐/无音乐/字幕/截图
各子文件夹的文件数量并计算综合完成率。这是交付完整性检测的核心口径，
且是纯文件系统只读统计，非常适合用临时目录测试（不依赖 Shell 复制）。
"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _mk_delivery_project(engine, name, total_eps=3):
    """在临时 group 下建项目 + 000交付 目录，写 DB，返回 000交付 目录路径。"""
    from sync_engine import SyncEngine
    group_root = engine.nas["group_root"]
    os.makedirs(group_root, exist_ok=True)
    gp = os.path.join(group_root, name)
    os.makedirs(gp, exist_ok=True)
    engine.db.upsert_project(name, "", gp, source_root="")
    if total_eps:
        engine.db.set_episodes(name, total_eps, total_eps)
    delivery = os.path.join(gp, "000交付")
    os.makedirs(delivery, exist_ok=True)
    return delivery


class TestDeliveryStats:
    def test_empty_delivery_folder(self, engine):
        """000交付 为空：found=False，各项 current=0。"""
        _mk_delivery_project(engine, "空项目", total_eps=3)
        r = engine.get_delivery_stats("空项目")
        assert r["found"] is False
        assert r["total_episodes"] == 3
        assert all(it["current"] == 0 for it in r["items"])
        assert r["overall_pct"] == 0

    def test_no_project_returns_default(self, engine):
        r = engine.get_delivery_stats("不存在")
        assert r["found"] is False
        assert r["items"] == []
        assert r["overall_pct"] == 0

    def test_counts_episode_folders(self, engine):
        """成片/字幕/有音乐 目录按文件名匹配统计文件数。"""
        d = _mk_delivery_project(engine, "P完整", total_eps=3)
        os.makedirs(os.path.join(d, "成片"), exist_ok=True)
        os.makedirs(os.path.join(d, "字幕"), exist_ok=True)
        os.makedirs(os.path.join(d, "有音乐"), exist_ok=True)
        for i in range(3):
            open(os.path.join(d, "成片", f"{i}.mp4"), "w").write("x")
        for i in range(2):
            open(os.path.join(d, "字幕", f"sub{i}.srt"), "w").write("x")
        for i in range(2):
            open(os.path.join(d, "有音乐", f"{i}.mp4"), "w").write("x")

        r = engine.get_delivery_stats("P完整")
        assert r["found"] is True
        by_key = {it["key"]: it["current"] for it in r["items"]}
        assert by_key["成片"] == 3
        assert by_key["有音乐"] == 2
        assert by_key["无音乐"] == 0
        assert by_key["字幕"] == 2
        assert by_key["截图"] == 0

    def test_overall_pct_only_checked_items(self, engine):
        """综合完成率只算设置了 total_episodes 的 episode 项 + 截图。"""
        d = _mk_delivery_project(engine, "P完成率", total_eps=2)
        # 成片 2 个 = total 2；有音乐 1 个；截图固定 total 5
        os.makedirs(os.path.join(d, "成片"), exist_ok=True)
        os.makedirs(os.path.join(d, "有音乐"), exist_ok=True)
        for i in range(2):
            open(os.path.join(d, "成片", f"{i}.mp4"), "w").write("x")
        open(os.path.join(d, "有音乐", "0.mp4"), "w").write("x")

        r = engine.get_delivery_stats("P完成率")
        # checked = 成片(2/2) + 有音乐(1/2) + 无音乐(0/2) + 字幕(0/2) + 截图(0/5)
        # = current 3 / max 13 → round(3/13*100)=23
        assert r["overall_pct"] == round(3 / 13 * 100)

    def test_delivery_stats_cache_hit(self, engine):
        """短时缓存：同项目 20s 内命中缓存不重扫目录。"""
        d = _mk_delivery_project(engine, "P缓存", total_eps=1)
        os.makedirs(os.path.join(d, "成片"), exist_ok=True)
        open(os.path.join(d, "成片", "0.mp4"), "w").write("x")
        r1 = engine.get_delivery_stats("P缓存")
        assert r1["found"] is True
        # 缓存应已写入
        assert "P缓存" in engine._delivery_stats_cache
        # 再次调用命中缓存
        r2 = engine.get_delivery_stats("P缓存")
        assert r2 == r1
