# -*- coding: utf-8 -*-
"""卡片「✏️ 调整分集」流程：替换项目分集 + 失效 episodes_status 缓存。

覆盖：
  - import_episodes 为整体覆盖（替换而非追加）
  - import_episodes 后 sync_engine 的 episodes_status / delivery_stats 缓存被清除
"""
import os
import sys
import pytest
from flask import Flask

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class _FakeSyncEngine:
    """带缓存的假 sync_engine，用于验证 import_episodes 会清缓存。"""
    def __init__(self):
        self._episode_status_cache = {"P1": (0.0, {"ok": True})}
        self._delivery_stats_cache = {"P1": (0.0, {"found": True})}


@pytest.fixture()
def ctx(tmp_db):
    from enhanced_routes import _register_enhanced_routes
    eng = _FakeSyncEngine()
    a = Flask(__name__)
    a.config["TESTING"] = True
    _register_enhanced_routes(a, tmp_db, sync_engine=eng)
    return {"client": a.test_client(), "db": tmp_db, "eng": eng}


def test_import_episodes_replaces_plan(ctx):
    db, client = ctx["db"], ctx["client"]
    db.upsert_project("P1", "", "")
    # 先写入旧分集
    client.post("/api/bulk/import_episodes",
                json={"project_name": "P1", "total_episodes": 5,
                      "assign": {"1": "张三", "2": "张三", "3": "李四"}})
    assert db.get_episode_plan("P1").get("1") == "张三"

    # 调整后替换（整体覆盖）：只保留 1、2，且换人
    r = client.post("/api/bulk/import_episodes",
                    json={"project_name": "P1", "total_episodes": 5,
                          "assign": {"1": "王五", "2": "王五"}})
    assert r.get_json()["ok"] is True
    plan2 = db.get_episode_plan("P1")
    assert plan2.get("1") == "王五"
    assert plan2.get("2") == "王五"
    assert "3" not in plan2, "整体覆盖：旧的第3集应被移除"


def test_import_episodes_clears_sync_engine_caches(ctx):
    client, eng = ctx["client"], ctx["eng"]
    assert "P1" in eng._episode_status_cache
    r = client.post("/api/bulk/import_episodes",
                    json={"project_name": "P1", "total_episodes": 3,
                          "assign": {"1": "张三"}})
    assert r.get_json()["ok"] is True
    assert "P1" not in eng._episode_status_cache, "import_episodes 后应清 episodes_status 缓存"
    assert "P1" not in eng._delivery_stats_cache, "import_episodes 后应清 delivery_stats 缓存"
