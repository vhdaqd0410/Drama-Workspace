# -*- coding: utf-8 -*-
"""/api/project/<name>/set_episodes 路由级测试（用 monkeypatch 替换 app 的 sync_engine）。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture()
def app_client(tmp_db, monkeypatch):
    """注册 app.py 的路由，并 monkeypatch 其 sync_engine 指向临时 db，固定 API key。"""
    import app as app_mod
    # 用一个最小 SyncEngine 替身，只暴露 db 供路由调用
    class _FakeEngine:
        def __init__(self, db):
            self.db = db
    monkeypatch.setattr(app_mod, "sync_engine", _FakeEngine(tmp_db))
    # 固定 API key，便于测试带鉴权头访问
    monkeypatch.setattr(app_mod, "_API_SECRET", "test-secret")
    app_mod.app.config["TESTING"] = True
    c = app_mod.app.test_client()

    # 包装 client 的 open，自动带鉴权头
    orig_open = c.open
    def _authed_open(*args, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        headers["X-API-KEY"] = "test-secret"
        kwargs["headers"] = headers
        return orig_open(*args, **kwargs)
    c.open = _authed_open
    return c


class TestSetEpisodesRoute:
    def test_update_both(self, app_client, tmp_db):
        tmp_db.upsert_project("P", "", "", source_root="")
        tmp_db.set_episodes("P", 30, 12)
        resp = app_client.post("/api/project/P/set_episodes",
                               json={"total": 40, "current": 15})
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["ok"] is True
        assert d["total_episodes"] == 40
        assert d["current_episodes"] == 15
        p = tmp_db.get_project("P")
        assert int(p["total_episodes"]) == 40

    def test_partial_update_preserves_total(self, app_client, tmp_db):
        tmp_db.upsert_project("Q", "", "", source_root="")
        tmp_db.set_episodes("Q", 20, 5)
        resp = app_client.post("/api/project/Q/set_episodes", json={"current": 7})
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["current_episodes"] == 7
        assert d["total_episodes"] == 20

    def test_project_not_found(self, app_client):
        resp = app_client.post("/api/project/不存在/set_episodes", json={"current": 1})
        assert resp.status_code == 404

    def test_bad_values_fall_back(self, app_client, tmp_db):
        """非数字 total/current 应忽略，保留原值。"""
        tmp_db.upsert_project("R", "", "", source_root="")
        tmp_db.set_episodes("R", 10, 3)
        resp = app_client.post("/api/project/R/set_episodes",
                               json={"total": "abc", "current": "高"})
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["total_episodes"] == 10
        assert d["current_episodes"] == 3
