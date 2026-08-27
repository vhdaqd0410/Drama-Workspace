# -*- coding: utf-8 -*-
"""阶段A：状态机收口测试 —— 状态白名单扩展、N审动态状态、状态变更审计。"""
import os
import sys
import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestReviewStatusHelpers:
    def test_is_review_status(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)
        assert m._is_review_status("二审中") is True
        assert m._is_review_status("三审中") is True
        assert m._is_review_status("十审中") is True
        assert m._is_review_status("审核中") is False  # 审核中是基础状态
        assert m._is_review_status("修改中") is False
        assert m._is_review_status("") is False

    def test_next_review_status(self):
        from deliver import DeliverMixin
        m = object.__new__(DeliverMixin)
        assert m._next_review_status("审核中") == "二审中"
        assert m._next_review_status("待提交审核") == "二审中"
        assert m._next_review_status("二审中") == "三审中"
        assert m._next_review_status("三审中") == "四审中"
        assert m._next_review_status("修改中") == "审核中"


class TestSetCustomStatus:
    def _mk_project(self, tmp_db, name):
        tmp_db.upsert_project(name, "", "", source_root="")

    def test_accepts_new_statuses(self, engine, tmp_db):
        """新流程状态应被接受：待提交审核、二审中、三审中。"""
        self._mk_project(tmp_db, "P1")
        ok, _ = engine.set_custom_status("P1", "待提交审核")
        assert ok is True
        assert tmp_db.get_project("P1")["custom_status"] == "待提交审核"
        ok, _ = engine.set_custom_status("P1", "修改中")
        assert ok is True
        ok, _ = engine.set_custom_status("P1", "二审中")
        assert ok is True
        assert tmp_db.get_project("P1")["custom_status"] == "二审中"

    def test_rejects_invalid_status(self, engine, tmp_db):
        self._mk_project(tmp_db, "P2")
        ok, msg = engine.set_custom_status("P2", "不存在的状态")
        assert ok is False
        assert "无效" in msg

    def test_status_change_writes_audit_log(self, engine, tmp_db):
        """状态变更应写入审计日志（供时间线）。"""
        self._mk_project(tmp_db, "P3")
        engine.set_custom_status("P3", "剪辑中")
        engine.set_custom_status("P3", "待提交审核")
        logs = tmp_db.get_audit_logs("P3")
        actions = [l.get("action") for l in logs]
        assert "状态变更" in actions
        # 审计日志里应记录 旧->新
        details = [l.get("detail") for l in logs if l.get("action") == "状态变更"]
        assert any("剪辑中" in d and "待提交审核" in d for d in details)
